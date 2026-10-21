import { Banner, Button, Disclosure, IconButton, Icon } from "@agent-console/ui";
import { useApi } from "../../../app/ApiContext";
import { useConnectionStatus } from "../../../app/useConnectionStatus";
import { describeError } from "../../../app/errors";
import { messages as m } from "../../../app/messages";
import { Skeleton } from "../Skeleton";
import { useBackends, useServerInfo } from "../settingsData";

function CopyRow({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td className="app-wrap">{children ?? value}</td>
      <td>
        <IconButton label={`${m.common.copy}: ${label}`} icon={<Icon name="copy" />} size="sm" onClick={() => void navigator.clipboard?.writeText(value)} />
      </td>
    </tr>
  );
}

/** ⑥ 서버 정보(읽기 전용). 토큰은 어떤 경우에도 표시하지 않는다. */
export function ServerSection() {
  const { meta, ws } = useApi();
  const connection = useConnectionStatus(ws);
  const info = useServerInfo();
  const backends = useBackends();
  const t = m.settings.server;
  if (info.isLoading) return <Skeleton rows={4} />;
  if (info.error) {
    return (
      <Banner tone="danger" actions={<Button size="sm" onClick={() => void info.refetch()}>{m.common.retry}</Button>}>
        {t.loadFailed}: {describeError(info.error, "").message}
      </Banner>
    );
  }
  const data = info.data!;
  const attrs = (data.attributes ?? {}) as Record<string, unknown>;
  const str = (k: string) => (attrs[k] === undefined || attrs[k] === null ? "" : String(attrs[k]));
  const origins = Array.isArray(attrs["allowed_origins"]) ? (attrs["allowed_origins"] as string[]) : [];
  const plugins = data.plugins ?? [];
  // 로딩 상태는 열린 문자열이다(모르는 값도 그대로 보인다). 오류가 있거나, 상태 정보 없이 읽지 못한 항목만 경고로 묶는다
  const broken = plugins.filter((p) => p.error != null || (p.status === undefined && p.loaded === false));
  const pluginText = (p: (typeof plugins)[number]) => [p.name, p.status].filter(Boolean).join(" · ");
  // 종류(group)별로 묶는다. 묶음 이름·순서는 서버가 준 값의 첫 등장 순서다
  const pluginGroups = plugins.reduce<{ group: string; items: typeof plugins }[]>((acc, p) => {
    const group = p.group ?? "";
    const found = acc.find((g) => g.group === group);
    if (found) found.items.push(p);
    else acc.push({ group, items: [p] });
    return acc;
  }, []);
  const bind = [str("host"), str("port")].filter(Boolean).join(":");
  return (
    <>
      <table className="app-table app-server-table" aria-label={m.settings.sections.server}>
        <tbody>
          <CopyRow label={m.connection.rowLabel} value={`${m.connection.state[connection]} — ${m.connection.note}`}>
            {m.connection.state[connection]}
            <div className="app-muted">{m.connection.note}</div>
          </CopyRow>
          <CopyRow label={t.rows.apiBaseUrl} value={meta.baseUrl} />
          <CopyRow label={t.rows.serverVersion} value={data.server_version} />
          <CopyRow label={t.rows.contractsVersion} value={data.contracts_version} />
          {str("workspace") === "" ? null : <CopyRow label={t.rows.workspace} value={str("workspace")} />}
          {bind === "" ? null : <CopyRow label={t.rows.bind} value={bind} />}
          {attrs["allow_remote"] === undefined ? null : <CopyRow label={t.rows.remote} value={attrs["allow_remote"] ? t.remoteOn : t.remoteOff} />}
          <CopyRow label={t.rows.allowedOrigins} value={origins.join(", ")}>{origins.length === 0 ? t.emptyOrigins : origins.join(", ")}</CopyRow>
          <CopyRow label={t.rows.backends} value={(backends.data ?? []).map((b) => b.id).join(", ")}>
            {(backends.data ?? []).map((b) => b.title).join(", ") || m.common.none}
          </CopyRow>
          {str("recovered_runs") === "" ? null : <CopyRow label={t.rows.recoveredRuns} value={str("recovered_runs")} />}
        </tbody>
      </table>
      <Disclosure summary={t.pluginsSummary(plugins.length)} className="app-server-plugins">
        {plugins.length === 0 ? (
          <p className="app-muted">{m.common.none}</p>
        ) : (
          <table className="app-table app-server-table" aria-label={t.rows.plugins}>
            {pluginGroups.map((g) => (
              <tbody key={g.group}>
                <tr>
                  <th scope="row">{g.group === "" ? m.common.none : g.group}</th>
                  <td className="app-wrap">
                    <ul className="app-server-plugin-list">
                      {g.items.map((p) => (
                        <li key={p.name}>{pluginText(p)}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              </tbody>
            ))}
          </table>
        )}
      </Disclosure>
      {broken.length > 0 ? (
        <Banner tone="warning" title={t.pluginsErrors}>
          <ul>
            {broken.map((p) => (
              <li key={`${p.group}:${p.name}`}>
                {p.name}: {p.error?.message ?? t.pluginError}
              </li>
            ))}
          </ul>
        </Banner>
      ) : null}
      <p className="app-muted">{t.tokenHidden}</p>
    </>
  );
}
