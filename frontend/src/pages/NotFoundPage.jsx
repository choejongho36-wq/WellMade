import { Link } from 'react-router-dom'
import './NotFoundPage.css'
import PageShell from '../components/PageShell.jsx'

function NotFoundPage() {
  return (
    <PageShell>
      <div className="notfound-split">
        <div className="notfound-left">
          <div className="page-index-tag">ERROR</div>
          <h1 className="notfound-title">요청하신 페이지를 찾을 수 없어요.</h1>
          <p className="notfound-sub">루트를 이탈한 모양입니다..</p>
          <Link to="/" className="notfound-cta">홈으로 돌아가기</Link>
        </div>
        <div className="notfound-right">
          <div className="notfound-band"></div>
          <div className="notfound-404">404</div>
          <div className="notfound-index">NOT FOUND</div>
        </div>
      </div>
    </PageShell>
  )
}

export default NotFoundPage
