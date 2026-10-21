import { Link } from "react-router";
import { messages as m } from "../app/messages";

/** 라우트 없음: 안내 + 첫 화면으로 가는 링크(첫 화면 경로는 라우트 설정 데이터에서 받는다). */
export function NotFoundScreen({ homePath }: { homePath: string }) {
  return (
    <div className="app-screen app-empty" data-screen="not-found">
      <h1 className="app-block-title">{m.notFound.title}</h1>
      <Link to={homePath} className="ac-btn" data-variant="primary" data-size="md">
        {m.notFound.toHome}
      </Link>
    </div>
  );
}
