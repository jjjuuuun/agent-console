# User guide

**English** | [한국어](USAGE.ko.md)

Installation and the first start are covered in the [README](README.md). This guide covers what you need to use the
app day to day.

## Contents

1. [First setup: connecting to Claude](#1-first-setup-connecting-to-claude)
2. [Using each feature](#2-using-each-feature)
   - [At a glance](#at-a-glance)
   - [Language](#language)
   - [Projects](#projects)
   - [Agents](#agents)
   - [Resources](#resources)
   - [Teams](#teams)
   - [Chat](#chat)
   - [Runs](#runs)
   - [Memory](#memory)
   - [Wiki](#wiki)
   - [Specs and templates](#specs-and-templates)
   - [Usage](#usage)
   - [Logs](#logs)
   - [Settings and feature modules](#settings-and-feature-modules)
   - [Import and export](#import-and-export)
3. [Running the server](#3-running-the-server)
4. [For developers](#4-for-developers)

## 1. First setup: connecting to Claude

Agents call Claude through the **Claude Agent SDK** execution backend (`claude-agent-sdk`).
**By default the backend signs in with your Claude subscription (the Claude Code sign-in). You can use an API key
instead.**

### Subscription sign-in (default)

**There is one sign-in per app.** The credentials are kept in one app-only folder inside the workspace (`--workspace`),
by default `<workspace>/.state/claude`, and every project shares them. Nothing is written to project folders for this.
The app passes this folder as `CLAUDE_CONFIG_DIR` to runs, connection tests and sign-in. When credentials are there they
are used automatically. When they are missing, the status card says that sign-in is required and shows where the
credentials are expected. **The sign-in in `~/.claude` is not used as a substitute** (it is separate from the Claude
Code sign-in in your terminal). The folder is created with mode 700 and the files with 600, and `.state/` is added to
the workspace `.gitignore` (the file is created if it does not exist and left alone otherwise). To change the location,
set `modules.options.mod-runs.backends.claude-agent-sdk.auth_dir.config_dir` (`null` follows the server environment).

- **From the app (on by default)**: open the **Backend connection** dialog from the sidebar
  ([shortcut below](#backend-connection-shortcut)), or go to *Settings › Agent defaults*, and select
  **[Sign in with subscription]** on the **Backend sign-in and readiness** card. The server starts `claude auth login` and relays the sign-in address and the
  code entry to the screen (*Sign in in the browser* → *Paste the code (if the browser shows one)* → *Confirm*). Claude
  Code writes the credentials to the app-only folder above. **The app never receives or stores the token.**
- **From a terminal**: point to the same folder. `CLAUDE_CONFIG_DIR=<workspace>/.state/claude claude auth login`

If you signed in with an earlier version that kept credentials elsewhere, the card asks you to sign in once more. The
old folder is not moved or deleted, so remove it yourself if you no longer need it. An agent with no `auth` setting at
all uses `ANTHROPIC_API_KEY` from the server environment when it is set.

To hide this button, set `modules.options.mod-runs.backend_login.enabled: false` in `agent-console.yaml`.

It has not been confirmed whether the terms of service allow using subscription credentials with the Agent SDK
(Anthropic's documentation recommends API keys for apps built on the Agent SDK). **Check the terms yourself and use it
at your own risk.** Every run with subscription credentials writes a warning to the log, and settings validation shows
a warning as well. To block subscription credentials entirely, turn them off in `agent-console.yaml`:

```yaml
modules:
  options:
    mod-runs:
      backends:
        claude-agent-sdk:
          allow_subscription_auth: false   # default true; false refuses runs that use the subscription
```

### Using an API key (optional)

Keep the key in an environment variable, never in a file. In settings, refer to it as `secret://anthropic_api_key`.
The server resolves this reference from the environment variable `anthropic_api_key`, then `ANTHROPIC_API_KEY`.

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # in your shell only; keep it out of settings files and commits
```

Then set the agent authentication to `auth: {mode: api_key, api_key: "secret://anthropic_api_key"}` (step 2 below).
To add a prefix to environment variable names, set `secrets.env_prefix` in `agent-console.yaml`
(for example `env_prefix: "AC_"` → `AC_ANTHROPIC_API_KEY`).
For the status card to check the API key as well, set the administrator setting `readiness.auth` to the same value.
The model list is fetched with this key too ([see below](#how-the-model-list-is-filled)):

```yaml
modules:
  options:
    mod-runs:
      backends:
        claude-agent-sdk:
          readiness:
            auth: {mode: api_key, api_key: "secret://anthropic_api_key"}
```

### Backend connection shortcut

The **Backend connection** button (a plug icon) is the first button in the row of icons at the bottom of the sidebar,
before help, theme and settings. Its badge shows the state of the default backend in the common settings (when no
default is set, the backend in the worst state); hover over it to see the backend name and a short summary. The same
dialog also opens from:

- the **Backend · {state}** chip in the header of the **Usage** screen (`g u`), next to the refresh button, and
- **Quick navigation** (`Ctrl+K`) → **Backend connection…** (there is no default keyboard shortcut).

The dialog shows the same cards as the **Backend sign-in and readiness** card in *Settings › Agent defaults*: the
status, **[Sign in with subscription]** (when the backend offers sign-in), **[Test connection]** and **[Check again]**,
so you can sign in and test without leaving the screen you are on. The default backend is at the top, marked
**Default**. For backends that can fetch their models, a line under the card shows how many models this account can use,
with **[Refresh]**; it refreshes by itself after you sign in. **More in Settings** closes the dialog and goes to the card
in *Settings › Agent defaults*.

The button, the chip and the command are left out when the server has no backend status feature (for example
`mod-runs` is off) or no backend that reports its status.

### Choosing the backend and model

1. In the web app, open *Settings › Agent defaults* and choose Claude Agent SDK as the backend, then a model and the
   authentication. The model field lists the models your account can use
   ([how the list is filled](#how-the-model-list-is-filled)); **Enter manually** takes any model id. The authentication
   default is the subscription (`subscription`); you can switch to an API key (`api_key`). In YAML this is the
   following shape in the workspace `settings.yaml`:

   ```yaml
   agent_defaults:
     backend: claude-agent-sdk
     model: <model id>
     backend_options:
       auth: {mode: subscription}
       # for an API key: auth: {mode: api_key, api_key: "secret://anthropic_api_key"}
   ```

2. On the same screen (or in the **Backend connection** dialog), check on the **Backend sign-in and readiness** card
   that the sign-in (or key) is picked up. By default the card checks the subscription sign-in (other authentication
   set per agent is checked when it runs). **[Test connection]** calls the model once for real, so it **costs a little
   (subscription usage or API charges)**. If a chat does not start, look here first.

You can also set the backend and model per team, agent or node. Empty values follow the defaults above.

### How the model list is filled

The model field (in *Settings › Agent defaults*, the agent editor and node settings) puts two lists together:

- **Models set in configuration**: the administrator list `backends.<id>.models` in `agent-console.yaml`. It is
  optional and empty by default (model ids are not built into the code).
- **Models from your account**: what the backend reports for the account it checks. Claude Agent SDK asks Claude Code
  for the models in its start-up information when you use the subscription, and the Anthropic Models API when you use an
  API key. **Neither calls a model, so fetching the list costs nothing.**

Configured models come first, in their order, and models found only for the account follow. When both lists have the
same id, they become one entry and the name and description you set win. Each option ends with where it came from:
**Config** or **Account** (or both). Whatever the list says, **Enter manually** still accepts any model id.

A line under the field shows the state of the list:

| Line | Meaning |
| --- | --- |
| *Fetching models…* | The lookup is running. You can keep typing |
| *N models from your account · as of …* **[Refresh]** | The account list is in. **[Refresh]** asks again right away |
| *Last fetched N models · as of … — couldn't refresh* | A newer lookup failed, so the last good list is still shown |
| *Couldn't fetch the model list. Only models set in configuration are shown.* | The lookup failed (the reason follows). **[Check connection…]** opens the Backend connection dialog (it does not call a model) |
| *Automatic model lookup is off. …* | The administrator turned the lookup off |
| *This sign-in method can't list models. …* | This backend or sign-in method has no model list. Use the configured models or type one |

- The first lookup happens when a model field first asks for the list, not when the server starts. The result is kept
  in server memory for one hour, and a failure for one minute. Signing in or out from the app clears the kept list, so
  the next lookup asks the account again. Nothing is saved to disk.
- A failed lookup never blocks the field: the configured models and **Enter manually** keep working.

To rename models, put them in your own order, or add models the account does not report, list them yourself:

```yaml
modules:
  options:
    mod-runs:
      backends:
        claude-agent-sdk:
          models:
            - {id: <model id>, title: <display name>}
```

The administrator turns the lookup off or changes its timing in `agent-console.yaml`:

```yaml
modules:
  options:
    mod-runs:
      model_discovery:
        enabled: true            # false = configured lists only
        ttl_s: 3600              # seconds a fetched list is reused (0 = ask on every request)
        failure_ttl_s: 60        # seconds a failure is reused before asking again
        timeout_s: 20            # maximum wait for one lookup, in seconds
        disabled_backends: []    # backend ids that are never looked up
      backends:
        claude-agent-sdk:
          model_discovery:
            method: auto         # auto, sdk_init (Claude Code start-up information) or models_api (Models API)
            api_base_url: null   # Models API address; null = ANTHROPIC_BASE_URL, then the official address
            api_version: "2023-06-01"   # the anthropic-version header
            page_limit: 1000     # models per page (1-1000)
```

With `method: auto`, the method follows the authentication that the status card checks (`readiness.auth`): an API key
uses `models_api`, the subscription uses `sdk_init`.

Known limits:

- The list follows the authentication that the status card checks (`readiness.auth`, the subscription by default).
  Agents that set a different `backend_options.auth` do not get a list of their own; type their model id.
- The subscription list is what the installed Claude Code CLI reports for its own model picker. A CLI version that
  reports no models shows *This sign-in method can't list models* (`unsupported`), and only configured models appear.
- When the app-only credentials folder has no sign-in (or the API key for `readiness.auth` is not set), the lookup does
  not start and the line shows a failure with the reason `auth_missing`. Sign in from the **Backend connection** dialog,
  and the list is fetched again.
- With `allow_subscription_auth: false`, the subscription lookup is refused as well (`subscription_disabled`).

## 2. Using each feature

### At a glance

```text
 Shared library                            Project (a registered folder)
 [Agents] [Resources] [Teams]   ── copy ─▶ project configuration ─▶ [Chat] ── 1 message = 1 run
 [Templates] [Wiki rules]                                             │
                                                                      ▼
 [Import] ── copy ─▶ agents, resources                              [Runs]  delegation flow, hooks, MCP
 [Export] ◀── agents, resources, teams                                │
                                     [Memory] [Wiki] [Specs]        [Logs] ── local logs ─▶ [Usage]

 [Settings]: defaults, language, log sources, feature modules
```

The menu on the left has three groups. **Shared library** (Teams, Agents, Resources, Templates, Wiki rules) holds the
originals that projects copy from. **Run** (Chat, Runs, Memory, Specs, Wiki) and **Observe** (Usage, Logs) show the
current project. Screens of feature modules that are turned off are left out of the menu.

- To move between screens, press `g` and then a letter: Chat `g c`, Runs `g h`, Memory `g m`, Specs `g e`, Wiki `g w`,
  Teams `g t`, Agents `g a`, Resources `g r`, Usage `g u`, Logs `g l`, Settings `g s`.
- `Ctrl+K` (`Cmd+K` on macOS) opens **Quick navigation** to find screens, items and actions. `?` lists the keyboard
  shortcuts. Change the keys in *Settings › Keyboard shortcuts*.
- When you type a new id, the app tells you right away if the name is reserved. Use another id.

### Language

1. Choose the language in *Settings › Appearance › Language*. You can also open **Quick navigation** (`Ctrl+K`) and
   choose **Change language…**.
2. The default is **Automatic (browser language)**: the first of your browser languages that the app has, or else the
   server default language (English unless the administrator changes it).
3. The choice is saved in the workspace settings (`ui.language` in `settings.yaml`), so every browser that connects to
   this server uses it.

- Only the app text changes. Names, descriptions, instructions and prompts you wrote, text written by agents, and log
  contents are never translated.
- A language marked **Partly translated** shows its missing text in the fallback language. Text that comes from the
  server (setting descriptions, kind names) appears in its original language when no message catalog covers it.
- The server administrator sets `modules.options.mod-i18n`: `default_language`, `fallback_language`, `catalog_dirs`
  (folders of your own `<language>.json` files, to change wording or add a language without changing code), and
  `disabled_catalogs` (catalogs to leave out). Plugins can ship their own message catalogs. The file format is described
  in [apps/server/README.md](apps/server/README.md) and the `ac-mod-i18n` package README.
- Terminal output (CLI help, server start messages, settings errors) is always in English.

### Projects

**One folder is one project.** Chat, runs, logs, memory, wiki and specs work only inside a registered project folder.
The shared library and settings work without a project.

1. In the sidebar **Projects** area, select **Add folder**, then pick the folder and a name in the **Add project folder**
   dialog. Registering creates `.agent-console/` in the folder (the settings file `project.yaml` and a `.gitignore`). If
   the folder already has one, nothing new is created: its configuration and records are loaded as they are.
2. In the project home, under **This project's configuration**, use **Copy from shared library…** to copy teams, agents
   and resources from the shared library, or create new ones in the project. The copies are stored inside the folder,
   so the folder works on its own.
3. Pick a project in the sidebar. Chat, runs, logs and memory then show that project.

**Unregister…** in the project menu only removes the registration. The files, configuration and records in the folder
are not deleted, and they show again when you register the same folder again. Unregistered projects can be viewed
read-only under *Settings › Projects* (*Unregistered projects*). If you moved the folder, use **Change path…** in the
menu. When the folder cannot be found or written to, the sidebar and the project home show the problem and how to fix
it.

### Agents

An agent holds a name, a role, instructions (the system prompt), a backend and model, and the resources attached to it.

1. **Agents** (`g a`) → **New agent** → set the name (and the id under the advanced options).
2. In the detail view, set the instructions, backend and model on the **Settings** tab, choose attached resources on the
   **Resources** tab, and save. Gray values are inherited from the common settings.

An agent runs only when it is placed as a node in a [team](#teams). Every save keeps a version that you can compare and
revert to.

### Resources

Resources are materials that several agents share: instructions, files, MCP servers, tool permissions and more. Plugins
can add new resource types.

1. **Resources** (`g r`) → **New resource** → choose a type, fill in the content and save.
2. In the detail view, check which agents and teams use the resource.

Attach it to an agent, or place it in a team as a resource node and connect it with a `uses` edge. A resource attached
to the common settings applies to every agent. Do not put secrets such as API keys in the content; refer to them as
`secret://<name>`.

### Teams

A team is a graph that connects user, agent and resource nodes to decide how work flows. The edge types below come with
the default plugin package; plugins can add more.

| Edge | Meaning |
| --- | --- |
| `message` / `reply` | Entry from the user / reply back to the user |
| `ask_user` | Question and approval: the agent asks you something or asks for approval during the run |
| `handoff` | Pass the result to the next agent (separate session, fixed order) |
| `subagent` | Delegate as a subagent (the caller gets the result back and continues) |
| `delegate` | Independent delegation (the target works in its own session) |
| `uses` | Attach a resource to an agent |
| `when` / `on_error` / `loop` | Condition / error path / loop |

You can also place a team inside a team (a nested team) as a node.

1. **Teams** (`g t`) → **New team** → choose how to start (*One user node*, *Empty team* or *Copy of a team*).
2. Use **Add** on the canvas (or `Alt+N`) to place agent, resource and user nodes. The picker groups items from this
   project, the shared library and other projects. Placing an agent connects the entry and reply edges automatically.
3. Drag from a node's handle and drop it on another node to create an edge. Select a node or an edge to change its type,
   conditions and settings in the panel on the right.
4. **Validate** shows problems (no entry, broken edges and so on) with suggested fixes. You can save with warnings, but a
   blocking problem stops you from starting a chat.
5. After saving, start a chat with this team from **Start chat ▸** or from [Chat](#chat).

### Chat

Inside a project, pick a team and talk to it. **Each message is one run.**

1. **Chat** (`g c`) → **New chat** → choose a team.
2. Send a message. If you send another while a run is in progress, by default it is queued and runs after the current
   turn ends.
3. When an agent asks a question, asks for tool approval or requests a review, a reply card appears in the conversation.
   Conversations that are waiting for you get a badge in the list.
4. Within one conversation the agent sessions continue, so the earlier context is kept.

From each turn you can go to its [run](#runs), and the tokens are counted in [Usage](#usage). Change the queue, reply
display and title rules in *Settings › Chat*.

### Runs

The list and details of every run. In **Runs** (`g h`), filter by status, team, agent and period, or start a run
without a chat using **New run**. Switch the view to **Handoffs** to see a table of how often each agent handed work to
another in recent runs. Opening a run shows the status of each node on the graph.

| Tab | Contents |
| --- | --- |
| Delegation flow | Delegation and handoffs drawn in time order (failed only, waiting for you included) |
| Agents | Runs and results per agent |
| hook · MCP | Hook executions, MCP server and tool calls, durations, errors |
| Interactions | Questions, approvals and review requests with their replies |
| Nodes and edges | Node inputs and outputs, edge decisions |
| Session logs | The log sessions that belong to this run (when [Logs](#logs) is on) |
| Architecture map | The run's events drawn as cells and connections (the drawing rules are the profiles in *Settings › Architecture map*) |

A team inside a team continues as a child run. Use the path at the top to move between parent and child runs.

### Memory

Memory is a shared record that agents and people read and write. Each project has its own (inside the project folder),
and the shared library has memory that you can copy into projects.

1. **Memory** (`g m`) → **New entry** → set the key, content and tags.
2. Filter by search text, tag and author (agent, person, or cleanup and import), and include archived entries when
   needed.
3. Agents read and write memory during runs when you attach a resource that gives memory access. The run detail shows how
   many reads and writes happened.

Set the scope kinds and cleanup rules in *Settings › Memory*. Move entries with **Export** and **Import…**.

### Wiki

A wiki is a set of linked Markdown pages stored in the project folder.

1. (Optional) In the shared library, open **Wiki rules** → **New wiki rule** to define what a wiki records, how it is
   checked and what instructions agents get, then copy the rule to the project. A wiki also works without rules.
2. **Wiki** (`g w`) → **New wiki…** → choose a name and rules, then create it. Rules are merged from the top down. To
   bring in an existing folder of Markdown files, use **Import (zip)…**.
3. Tabs: **Page** (view and edit), **Graph** (link graph), **Checks** (rule check results), **Rules** (wiki info plus the
   merged instructions, rules and syntax).
4. For an agent to manage the wiki, attach the “Wiki” resource to that agent in the team.

Changes made in the app show right away. Files edited in another editor can show up to one freshness window later (2
seconds by default), and **Rescan** checks right away and records the outside changes. The server administrator changes
this with `modules.options.mod-wiki.freshness_seconds` (0 checks on every request) and `scan_interval_seconds` (reread
opened wikis at an interval). If the folder is not writable, the wiki is view-only.

### Specs and templates

A spec is a set of documents stored in the project folder; the tasks in those documents are tracked and can be run. A
template is shared library configuration that fills in the document list and rules when you create a spec.

1. In the shared library, open **Templates** → **New template**. The editor tabs are **Rules**, **Skeleton files** and
   **Versions**. On the **Versions** tab you compare a saved version with the current one, or two versions with each
   other, and go back with **Revert…**. You can also create a template with “Save as template” from a project's
   documents.
2. In a project, open **Specs** (`g e`) → **New spec…** → choose a template (or a blank spec). If the project has no
   templates, copy one from the shared library in the same dialog. To bring in existing Markdown documents, use
   **Import from folder…**.
3. Tabs: **Documents**, **Tasks** (task states and runs), **Plan** (dependency graph, batches of tasks that can start
   together, and the longest dependency chain), **Trace** (requirements ↔ tasks ↔ runs) and **Rules**.
4. With **Auto-advance** on, ready tasks start automatically as earlier tasks finish. Runs that cost money may start with
   nobody present, so set the limits before you turn it on. Running tasks needs the runs integration to be on.

Set defaults such as the task syntax and verification sources in *Settings › Specs*; each spec can override them on its
**Rules** tab.

### Usage

Shows the 5-hour and weekly usage windows and token totals. Values that a source does not provide are never made up.
The usage windows cover the whole account (they cannot be split by project); the token totals are for the current
project.

- Sources: runs in Agent Console, Claude Code logs on this PC (through the [Logs](#logs) feature), and the Claude Code
  status line bridge.
- Check them in the **Sources** panel of **Usage** (`g u`), and change how they are shown in *Settings › Usage*.
- If usage stays empty because the backend is not signed in, the **Backend · {state}** chip in the header opens the
  [Backend connection](#backend-connection-shortcut) dialog.
- To include Claude Code usage, register the command below as the Claude Code statusLine command. Edit
  `~/.claude/settings.json` yourself (Agent Console does not write to `~/.claude`). The guide on the usage screen builds
  the snippet to paste.

  ```bash
  uv run agent-console statusline --output <workspace>/.state/usage/statusline.json
  ```

### Logs

Reads logs from other tools such as Claude Code, plus the app's run history, and indexes them in one format. **Original
logs are only read.**

1. Turn on a source in *Settings › Log sources* (`claude-code-jsonl`, off by default). Turning it on tells you that the
   source contents, including conversation text, are copied into this app's index. Values that look like secrets are
   masked before saving, but not perfectly.
2. **Only sessions of project folders registered in the app are collected** (subfolders included). With no registered
   projects nothing is collected, and the screen asks you to add a project first. The app reads CLI sessions in
   `~/.claude/projects` (read-only; the only thing the app reads from `~/.claude`) and the sessions it ran itself in
   `<workspace>/.state/claude/projects` (source setting `workspace_roots`). Even if you set `roots` yourself, only records
   of registered projects are read. Log-based usage estimates use this index too, so they count only sessions of
   registered projects.
3. Open **Logs** (`g l`). Collection starts automatically, and **Collect now** reads right away. The list shows the
   sessions of the current project.
4. Play back a session on the **Sessions** tab, filter by category, source, project and model on the **Search** tab, and
   arrange widgets on the **Dashboards** tab.
5. **Download archive** (HTML and JSON) creates a file you can open offline.

Change category names, colors and visibility in *Settings › Log classification*. The collection interval and retention
period are set in `modules.options.mod-logs` in `agent-console.yaml`.

### Settings and feature modules

**Settings** (`g s`) are user settings stored in the workspace. Settings are overridden in the order **Common → Project
→ Team → Agent → Node**, and empty values follow the layer above. Edit the project layer with **Settings for this
project…** in the project home menu. Changed settings apply from the next run, and every save keeps a version.

Each server feature is a module. See the list and states in *Settings › Feature modules* or at `GET /api/v1/modules`
(read-only in the web app). Modules are turned on and off by whoever starts the server:

```bash
uv run agent-console serve --disable-module mod-logs
```

In the settings file, write `modules.disabled: [mod-logs]`. The command line wins over the settings file.

| Module | Feature |
| --- | --- |
| `mod-definitions` · `mod-resources` | Agent, team and resource definitions, and settings |
| `mod-runs` | Run engine, run history and backend sign-in |
| `mod-chat` | Chat |
| `mod-projects` | Projects |
| `mod-memory` | Memory |
| `mod-wiki` | Wiki and wiki rules |
| `mod-sdd` | Specs and templates |
| `mod-usage` | Usage |
| `mod-logs` | Log collection and index |
| `mod-architecture` | Architecture map |
| `mod-i18n` | Message catalogs (languages) |
| `mod-imports` · `mod-exports` | Import and export |
| `mod-versions` | Definition and settings versions |
| `link-*` | Integrations that connect two features (for example `link-logs-usage`) |

Turning a feature off stops only the integrations connected to it; everything else keeps working.

### Import and export

**Import.** Copies agents and resources from an existing Claude Code project setup (`.claude/`, `CLAUDE.md`,
`.mcp.json`). The originals are only read. The user-wide configuration (`~/.claude`) is not imported. If the old setting
`modules.options.mod-imports.home` is still present, the server refuses to start and explains what to change.

1. On the **Resources** screen, select **Import…** to open **Import from .claude**. When you pick a project in the
   sidebar, the sources in that project folder appear.
2. **Choose source** → **Choose items**: pick what to import from the list that was read, and decide what happens on a
   name conflict (*Skip*, *Use a new name* or *Overwrite*). Nothing is written up to this step.
3. Check the imported items under **Result**. Values that look like secrets (MCP `env`, `headers` and so on) are marked
   and not saved as they are; after importing, replace them with `secret://<name>` references.

**Export.** Exports agents, resources and teams in another tool's format. Formats come from plugins; the default
package provides the Claude Code project layout (`.claude/agents`, `.claude/skills`, `.claude/settings.json`,
`CLAUDE.md`, `.mcp.json`).

1. From the menu of an agent or resource detail view, or of the team editor, select **Export…**.
2. Go through **Format** → **Items and options** → **Preview** (check the files to be created and any conflicts) →
   **Destination**. The saved version is exported; unsaved changes are not included.
3. The default is a zip download. Writing straight into a folder works only for folders allowed in the server settings,
   and protected locations such as `~/.claude` are never written to.

Exporting a team also bundles the agents, resources and child teams it uses. Wikis, specs and memory have their own
export and import on their screens.

## 3. Running the server

- **Runs keep going when you close the browser.** The server owns the runs, so when you open the app again the history
  is all there.
- **Where things are stored.** The shared library (agents, teams, resources, templates, wiki rules) and the common
  settings (`settings.yaml`) are YAML files in the workspace folder (default `.agent-console/`). The app database
  (shared library versions, log index, usage samples), the sign-in credentials and run files are under
  `.agent-console/.state/`. A project's configuration copies, project settings, chat and run records, memory, wiki pages
  and spec documents are **inside the project folder** (`<folder>/.agent-console/` and so on). Change the workspace with
  `workspace` in `agent-console.yaml`. To back up, copy the workspace and the project folders.
- **Restarting.** Restarting the server interrupts turns in progress. In the chat, select **[Rerun from here]** on that
  turn to continue from the node you pick. Queued messages are put on hold; handle them with **Run all** or **Cancel
  all** in the banner.
- **Port and binding.** The default is `127.0.0.1:8765`. Change it with `serve --host` and `--port`, or `host` and `port`
  in `agent-console.yaml`. Listening outside `127.0.0.1` also needs `security.allow_remote: true`; decide for yourself
  before exposing the server.
- **Settings file.** The server starts with defaults even without a settings file. To change settings, copy the example
  with `cp agent-console.example.yaml agent-console.yaml` and edit it. The server reads `agent-console.yaml` in the current
  folder; give another path with `--config <path>` or `AGENT_CONSOLE_CONFIG`. Precedence is
  `command line > AGENT_CONSOLE_* environment variables > settings file > defaults`. Each key is described in the comments
  of the example file and in [apps/server/README.md](apps/server/README.md). If the file has unknown or removed keys, the
  server does not start and explains what to change.
- **Serving the web app from the settings file.** Instead of environment variables, you can write
  `web: {serve_static: true, static_dir: apps/web/dist}` in the settings file.
- **Ready check.** The server is ready when `GET /api/v1/health` returns 200.

## 4. For developers

Run all checks with `uv run poe check` (ruff, mypy, import-linter, pytest) and `pnpm check` (ESLint, tsc, Vitest,
dependency-cruiser). When you work on the UI, start the server (127.0.0.1:8765) and a web preview (127.0.0.1:4173)
together with `pnpm app` (`--build` rebuilds the web app, and arguments after `--` go to `serve`), or start
`uv run agent-console serve` and `pnpm --filter @agent-console/web dev` (5173) separately.
The development rules and the full command list are in `CLAUDE.md` at the root, the workflow is in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), and the extension points are in [docs/extending/](docs/extending/README.md).
