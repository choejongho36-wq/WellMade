import './MainPage.css'
import Sidebar, { useAuth } from './Sidebar.jsx'

const GOAL_LABEL = {
  LOSE: '체중 감량',
  GAIN: '근육 증가',
  MAINTAIN: '체중 유지',
}

const PROVIDER_LABEL = {
  GOOGLE: '구글',
  KAKAO: '카카오',
  NAVER: '네이버',
}

function MyPage() {
  const { user, profile } = useAuth()

  return (
    <div className="app revealed">
      <Sidebar />

      <main className="main">
        <div className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">MY WELLMADE</div>
              <div className="section-title">마이페이지</div>
            </div>
          </div>

          {user ? (
            <div className="pcard">
              <div className="pcard-body">
                <div className="pcard-title">{profile?.name ?? '이름 미설정'}</div>
                <p className="pcard-desc">이메일: {user.email}</p>
                <p className="pcard-desc">로그인 방식: {PROVIDER_LABEL[user.provider] ?? user.provider}</p>
                <p className="pcard-desc">목표: {profile?.goal ? GOAL_LABEL[profile.goal] : '설정 전'}</p>
              </div>
            </div>
          ) : (
            <p className="pcard-desc">로그인 후 프로필을 확인할 수 있습니다.</p>
          )}
        </div>
      </main>
    </div>
  )
}

export default MyPage
