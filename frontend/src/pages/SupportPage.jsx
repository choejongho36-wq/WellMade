import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import './SupportPages.css'

// 고객센터 허브 - Roomie(다른 팀 프로젝트) SupportPage 구조를 참고해 WellMade에 맞게 구성.
// "외부 채팅/통화 연결"은 실제 상담 서비스를 붙이지 않고 껍데기만 둔다(안내 문구만 표시).
export default function SupportPage() {
  return (
    <PageShell>
      <div className="support-page">
        <h1 className="support-title">고객센터</h1>
        <p className="support-subtitle">궁금한 점을 빠르게 해결해드릴게요.</p>

        <div className="support-grid">
          <Link to="/faq" className="support-card">
            <h2>자주 묻는 질문</h2>
            <p>많이 물어보시는 질문과 답변을 모아뒀어요.</p>
            <span className="support-card-link">FAQ 보러가기 →</span>
          </Link>

          <Link to="/inquiry" className="support-card">
            <h2>1:1 문의</h2>
            <p>궁금한 점을 직접 남겨주시면 확인 후 답변해드려요.</p>
            <span className="support-card-link">문의 게시판 가기 →</span>
          </Link>

          <Link to="/notices" className="support-card">
            <h2>공지사항</h2>
            <p>서비스 업데이트와 안내 사항을 알려드려요.</p>
            <span className="support-card-link">공지사항 보러가기 →</span>
          </Link>

          <div className="support-card support-card-disabled">
            <h2>채팅·전화 상담</h2>
            <p>실시간 채팅/전화 상담을 준비하고 있어요.</p>
            <span className="support-note">준비 중</span>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
