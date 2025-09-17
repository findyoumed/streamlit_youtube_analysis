import os
import time
from typing import List, Dict, Any

import requests
import streamlit as st
from dotenv import load_dotenv


# -----------------------------
# 환경 설정
# -----------------------------
# 1) 배포/Cloud에서는 .streamlit/secrets.toml의 st.secrets 값을 사용
# 2) 로컬 개발에서는 .env(.dotenv) 값으로 폴백
load_dotenv()  # .env 로드 (로컬 개발 편의)

def _get_secret(name: str, default: str = "") -> str:
    try:
        # st.secrets는 Mapping 형태이며 존재하지 않으면 KeyError 발생 가능
        if name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return str(os.getenv(name, default)).strip()

API_KEY = _get_secret("YOUTUBE_API_KEY", "")
DEFAULT_REGION = _get_secret("REGION_CODE", "KR") or "KR"
MAX_RESULTS = 30

# 지역 코드 예시(대표 국가) — 코드와 한글명 매핑
REGION_OPTIONS = [
    ("KR", "대한민국"), ("US", "미국"), ("JP", "일본"), ("IN", "인도"), ("GB", "영국"),
    ("DE", "독일"), ("FR", "프랑스"), ("BR", "브라질"), ("MX", "멕시코"), ("CA", "캐나다"),
    ("AU", "호주"), ("VN", "베트남"), ("TH", "태국"), ("ID", "인도네시아"), ("TR", "튀르키예"),
    ("SA", "사우디아라비아"), ("AE", "아랍에미리트"), ("ES", "스페인"), ("IT", "이탈리아"), ("RU", "러시아"),
]
REGION_NAME_MAP = {code: name for code, name in REGION_OPTIONS}
REGION_CODES = [code for code, _ in REGION_OPTIONS]


# -----------------------------
# 유틸리티
# -----------------------------
def format_views(n: str | int) -> str:
    try:
        v = int(n)
    except Exception:
        return str(n)

    # 한국어 축약: 만, 억 단위 간단 표기
    if v >= 100_000_000:
        return f"{v/100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v/10_000:.1f}만"
    return f"{v:,}"


@st.cache_data(ttl=60)  # 60초 캐시
def get_most_popular_videos(api_key: str, region_code: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """
    YouTube Data API (v3) - videos.list
    chart=mostPopular 기반으로 인기 동영상 조회

    Returns: items list (빈 리스트 가능)
    Raises: requests.HTTPError 외 일반 예외
    """
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=15)
    # HTTP 레벨 에러 처리
    if not resp.ok:
        try:
            data = resp.json()
        except Exception:
            data = {"error": {"message": resp.text}}
        raise requests.HTTPError(f"YouTube API HTTP {resp.status_code}: {data}")

    data = resp.json()
    # API 응답 내 에러 처리
    if "error" in data:
        raise RuntimeError(f"YouTube API Error: {data['error']}")

    return data.get("items", [])


@st.cache_data(ttl=120)
def get_channel_subscribers(api_key: str, channel_ids: List[str]) -> Dict[str, int]:
    """channels.list로 채널 구독자 수를 조회하여 {channelId: subscriberCount} 형태로 반환합니다.
    최대 50개까지 한 번에 조회 가능. 일부 채널은 구독자수가 비공개일 수 있습니다.
    """
    if not channel_ids:
        return {}

    # 중복 제거 및 50개 단위로 분할
    unique_ids = list({cid for cid in channel_ids if cid})
    result: Dict[str, int] = {}

    url = "https://www.googleapis.com/youtube/v3/channels"
    for i in range(0, len(unique_ids), 50):
        batch = unique_ids[i : i + 50]
        params = {
            "part": "statistics",
            "id": ",".join(batch),
            "key": api_key,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            if not resp.ok:
                # 배치 단위 에러는 로그만 남기고 계속
                try:
                    data = resp.json()
                except Exception:
                    data = {"error": {"message": resp.text}}
                st.warning(f"채널 통계 조회 오류(HTTP {resp.status_code}): {data}")
                continue
            data = resp.json()
            for ch in data.get("items", []):
                cid = ch.get("id")
                stats = (ch or {}).get("statistics", {})
                subs = stats.get("subscriberCount")
                if cid and subs is not None:
                    try:
                        result[cid] = int(subs)
                    except Exception:
                        pass
        except Exception as e:
            st.warning(f"채널 통계 조회 중 오류: {e}")
            continue
    return result


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="YouTube 인기 동영상", page_icon="▶️", layout="wide")

# -----------------------------
# 인증 (세션 기반 로그인)
# -----------------------------
EXPECTED_USER = _get_secret("AUTH_USERNAME", "")
EXPECTED_PASS = _get_secret("AUTH_PASSWORD", "")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def logout():
    st.session_state.authenticated = False
    # 민감정보가 남지 않도록 비밀번호 입력값도 초기화 시도
    st.session_state.pop("_login_user", None)
    st.session_state.pop("_login_pass", None)
    st.rerun()

with st.sidebar:
    st.subheader("🔐 로그인")
    if not st.session_state.authenticated:
        user = st.text_input("아이디", key="_login_user")
        pw = st.text_input("비밀번호", type="password", key="_login_pass")
        login_btn = st.button("로그인")
        if login_btn:
            if EXPECTED_USER and EXPECTED_PASS and user == EXPECTED_USER and pw == EXPECTED_PASS:
                st.session_state.authenticated = True
                st.success("로그인 성공")
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
        st.caption("관리자는 .streamlit/secrets.toml에서 자격 정보를 설정하세요.")
    else:
        st.success("로그인됨")
        st.button("로그아웃", on_click=logout)

# 인증이 되지 않은 경우 메인 콘텐츠 차단
if not st.session_state.authenticated:
    st.title("접근 제한")
    st.info("이 앱을 사용하려면 좌측 사이드바에서 로그인해주세요.")
    st.stop()

st.title("🔥 유튜브 인기 동영상")
st.caption("YouTube Data API v3 • 지역 기반 인기 콘텐츠 • 캐시 60초")

# 세션 상태 초기화 및 콜백 정의
if "region_sel" not in st.session_state:
    st.session_state.region_sel = "KR"
if "region_custom" not in st.session_state:
    st.session_state.region_custom = (DEFAULT_REGION or "KR").upper()

def _on_select_region_change():
    # 예시 선택 시 커스텀 입력값을 동일하게 맞춰줌
    st.session_state.region_custom = str(st.session_state.region_sel).upper()

def _on_custom_region_change():
    # 커스텀 입력을 항상 대문자로 정규화
    st.session_state.region_custom = str(st.session_state.region_custom or "KR").upper()

# 상단 컨트롤 바
with st.container():
    col1, col2, col3, col4 = st.columns([1.2, 1.2, 1, 1.4])
    with col1:
        st.selectbox(
            "지역 코드 (예시)",
            options=REGION_CODES,
            index=REGION_CODES.index("KR") if "KR" in REGION_CODES else 0,
            help="대표 지역 예시. 아래 입력란으로 커스텀 코드 사용 가능",
            key="region_sel",
            on_change=_on_select_region_change,
            format_func=lambda c: f"{c} - {REGION_NAME_MAP.get(c, c)}",
        )
    with col2:
        st.text_input(
            "커스텀 지역 코드",
            max_chars=2,
            help="ISO 3166-1 alpha-2, 예: KR, US, JP, IN, GB, DE, FR, BR, MX, CA, AU",
            key="region_custom",
            on_change=_on_custom_region_change,
        )
        region = (st.session_state.region_custom or st.session_state.region_sel or "KR").upper()
    with col3:
        max_count = st.selectbox("표시 개수", options=[10, 20, 30, 40, 50], index=1)
    with col4:
        refresh = st.button("🔄 새로고침", help="캐시를 비우고 최신 결과를 불러옵니다")

# (요청에 따라) 지역 코드 예시 확장 섹션 제거

if refresh:
    st.cache_data.clear()
    st.toast("캐시를 비웠습니다. 다시 불러오는 중…", icon="🔄")
    time.sleep(0.2)

# 사전 검증: API 키
if not API_KEY:
    st.error(
        "YOUTUBE_API_KEY가 설정되지 않았습니다.\n"
        "- 배포/클라우드: .streamlit/secrets.toml에 YOUTUBE_API_KEY를 설정하세요.\n"
        "- 로컬 개발: .env 파일에 YOUTUBE_API_KEY를 설정하세요."
    )
    st.stop()

# 데이터 로드 및 에러 처리
try:
    items = get_most_popular_videos(API_KEY, region, max_count)
except requests.HTTPError as http_err:
    st.error(f"HTTP 오류가 발생했습니다: {http_err}")
    st.stop()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

if not items:
    st.warning("표시할 동영상이 없습니다. 지역 코드를 확인하거나 잠시 후 다시 시도해주세요.")
    st.stop()


# 채널 구독자 수 조회 (배치)
channel_ids = [((it.get("snippet") or {}).get("channelId")) for it in items]
subs_map = get_channel_subscribers(API_KEY, channel_ids)

# 결과 렌더링
st.subheader(f"지역: {region.upper()} • 총 {len(items)}개")

for i, item in enumerate(items, start=1):
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    title = snippet.get("title", "(제목 없음)")
    channel = snippet.get("channelTitle", "(채널 정보 없음)")
    channel_id = snippet.get("channelId")
    thumbs = snippet.get("thumbnails", {})
    thumb = (
        thumbs.get("medium")
        or thumbs.get("high")
        or thumbs.get("standard")
        or thumbs.get("default")
        or {}
    )
    thumb_url = thumb.get("url")

    views = stats.get("viewCount", "0")
    likes = stats.get("likeCount")  # 공개되지 않을 수 있음
    comments = stats.get("commentCount")
    subs = subs_map.get(channel_id)

    video_id = item.get("id") if isinstance(item.get("id"), str) else item.get("id")
    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None

    with st.container():
        cols = st.columns([1, 5])
        with cols[0]:
            if thumb_url:
                st.image(thumb_url, use_container_width=True)
            else:
                st.write("(썸네일 없음)")
        with cols[1]:
            # 제목 (클릭 가능)
            if video_url:
                st.markdown(f"**{i}. [{title}]({video_url})**")
            else:
                st.markdown(f"**{i}. {title}**")

            # 한 줄 간단 표기: 채널 • 조회수 • 좋아요 • 댓글 • (구독자 1회만)
            parts = [f"{channel}", f"👁 {format_views(views)}"]
            if likes is not None:
                parts.append(f"👍 {format_views(likes)}")
            if comments is not None:
                parts.append(f"💬 {format_views(comments)}")
            if subs is not None:
                parts.append(f"👤 {format_views(subs)}명")
            compact_line = " · ".join(parts)
            st.markdown(
                f"<span style='font-size:0.9rem;color:#666'>{compact_line}</span>",
                unsafe_allow_html=True,
            )

    # 얇은 구분선으로 세로 간격 최소화
    st.markdown("<hr style='margin:6px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

st.success("불러오기 완료 ✅")
