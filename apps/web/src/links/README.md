# apps/web/src/links

The integration layer for parts that use two or more features together. Whether an integration part is shown depends on whether the modules and roles it needs are on (otherwise it is hidden or disabled).

- `linkParts.ts`: integration part registration data (part id, required module ids and roles, hidden or disabled). Screens know only the part id.
- A component that uses two features goes in `links/<a>-<b>/`. Feature folders (`features/*`) do not import this folder;
  the app assembly layers (`app/`, `shell/`) use it.
- Whether a part is on is decided only through `useLinkPart` and `LinkPart` in `modules/`.
