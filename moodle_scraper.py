"""
Moodle にログインし、カレンダー／ダッシュボードから課題一覧を取得する。
"""
import logging
import re
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import pyotp
import requests
from bs4 import BeautifulSoup

from config import ACCESS_INTERVAL, MOODLE_PASSWORD, MOODLE_URL, MOODLE_USER, PROJECT_ROOT, REQUEST_TIMEOUT, TOTP_SECRET
from models import Assignment

logger = logging.getLogger(__name__)

# セッションのタイムアウト（config から取得）


def _wait_between_requests() -> None:
    """学校サーバーへの負荷軽減・バグ時の連打防止のため、アクセス間に待機する"""
    if ACCESS_INTERVAL > 0:
        time.sleep(ACCESS_INTERVAL)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "MoodleReminder/1.0 (Python; Windows)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
    })
    return s


def _find_login_link(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    """ページ内の「ログイン」リンクを探す。右上・ヘッダーを優先し、テキスト・href・aria-label・img alt を判定。"""
    def link_text_and_attrs(elem):
        text = elem.get_text(strip=True)
        aria = (elem.get("aria-label") or elem.get("title") or "").strip()
        img = elem.find("img")
        alt = (img.get("alt") or img.get("title") or "").strip() if img else ""
        return text, aria, alt

    def is_login_candidate(a_tag):
        href = (a_tag.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:") or "mailto:" in href:
            return False, None
        h_lower = href.lower()
        if "login" in h_lower or "signin" in h_lower or "auth" in h_lower:
            return True, href
        text, aria, alt = link_text_and_attrs(a_tag)
        combined = " ".join([text, aria, alt]).lower()
        if "ログイン" in text or "ログイン" in aria or "ログイン" in alt:
            return True, href
        if "login" in combined or "log in" in combined or "サインイン" in combined or "sign in" in combined:
            return True, href
        return False, None

    # 1) ヘッダー・ナビ内を優先（右上は多くのテーマで header / nav 内）
    for container in soup.find_all(["header", "nav"], limit=5):
        for a in container.find_all("a", href=True):
            ok, href = is_login_candidate(a)
            if ok and href:
                return urljoin(current_url, href)
    # 2) クラスでログイン・ユーザーメニューっぽい要素内
    for container in soup.find_all(class_=re.compile(r"login|user|menu|nav|header", re.I)):
        for a in container.find_all("a", href=True):
            ok, href = is_login_candidate(a)
            if ok and href:
                return urljoin(current_url, href)
    # 3) ページ全体で href に login が含まれるリンク
    for a in soup.find_all("a", href=True):
        ok, href = is_login_candidate(a)
        if ok and href:
            return urljoin(current_url, href)
    return None


def _login_direct(session: requests.Session) -> bool:
    """Moodle に直接ログイン（ID/パスワード形式）。"""
    base = MOODLE_URL.rstrip("/")
    # 段階1: トップページに到達
    try:
        r = session.get(base + "/", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        _wait_between_requests()
    except requests.RequestException as e:
        logger.exception("[段階1] トップページに到達できませんでした: %s", e)
        return False
    logger.info("[段階1] トップページに到達しました (URL=%s)", r.url)

    soup = BeautifulSoup(r.text, "html.parser")
    current_url = r.url
    login_page_url = current_url

    # このページにすでにログインフォームがあるか先に判定するための関数を定義
    def _form_has_password_and_user(f) -> bool:
        has_pass = any(inp.get("type") == "password" for inp in f.find_all("input"))
        if not has_pass:
            return False
        name_lower = lambda inp: (inp.get("name") or inp.get("id") or "").lower()
        has_user = any(
            any(x in name_lower(inp) for x in ("username", "user", "j_username", "email", "login", "eid", "uid", "id", "omuid"))
            for inp in f.find_all("input")
        )
        has_token = any(inp.get("name") == "logintoken" for inp in f.find_all("input"))
        text_inputs = [inp for inp in f.find_all("input") if inp.get("type") in ("text", "email", None)]
        return has_user or has_token or len(text_inputs) >= 1

    def _get_form(s):
        f = s.find("form", id="login") or s.find("form", class_=re.compile(r"login"))
        if f:
            return f
        f = s.find("form", action=re.compile(r"login"))
        if f:
            return f
        for x in s.find_all("form"):
            if _form_has_password_and_user(x):
                return x
        # 最終 fallback: パスワード入力が1つでもあるフォーム（ログインページは通常1つだけ）
        for x in s.find_all("form"):
            if any(inp.get("type") == "password" for inp in x.find_all("input")):
                return x
        # OMU LMS 用: name="OMUID" を含むフォームを明示的に探す（SSO 等で構造が異なる場合）
        for x in s.find_all("form"):
            if any((inp.get("name") or "").upper() == "OMUID" for inp in x.find_all("input")):
                return x
        return None

    def _is_sso_gateway_form(f) -> bool:
        """SSO ゲートウェイか（hidden のみで auth サーバへ POST するフォーム）"""
        action = (f.get("action") or "").lower()
        if "auth" not in action and "sso" not in action:
            return False
        has_hidden = any(inp.get("type") == "hidden" for inp in f.find_all("input"))
        has_user_or_pass = any(
            inp.get("type") in ("text", "password") or "user" in (inp.get("name") or "").lower() or "pass" in (inp.get("name") or "").lower()
            for inp in f.find_all("input")
        )
        return has_hidden and not has_user_or_pass

    form = _get_form(soup)
    if form:
        logger.info("[段階2] トップページにログインフォームがありました。そのまま利用します")
    if not form:
        login_link = _find_login_link(soup, current_url)
        if login_link:
            logger.info("[段階2] ログインリンクを検出しました。ログインページへ移動します (%s)", login_link)
            try:
                r = session.get(login_link, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                _wait_between_requests()
                soup = BeautifulSoup(r.text, "html.parser")
                login_page_url = r.url
                form = _get_form(soup)
                if not form:
                    logger.info(
                        "[段階2] ログインリンク先のページにフォームを検出できませんでした。最終 URL=%s（SSO でリダイレクトされた可能性）",
                        r.url,
                    )
            except requests.RequestException as e:
                logger.warning("[段階2] ログインリンク先の取得に失敗: %s", e)
        if not form:
            logger.info("[段階2] login/index.php を直接取得してフォームを探します")
            try:
                r = session.get(f"{base}/login/index.php", timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                _wait_between_requests()
                soup = BeautifulSoup(r.text, "html.parser")
                login_page_url = r.url
                form = _get_form(soup)
            except requests.RequestException as e:
                logger.exception("[段階2] ログインページに到達できませんでした: %s", e)
                return False

    # SSO ゲートウェイが複数段ある場合に備え、ログインフォームが出るまでループ
    max_gateway_loops = 5
    for _ in range(max_gateway_loops):
        if form:
            break
        gateway_form = soup.find("form", action=re.compile(r"auth|sso|AuthServer|MultiAuth", re.I))
        if not gateway_form or not _is_sso_gateway_form(gateway_form):
            break
        logger.info("[段階2] SSO ゲートウェイを検出しました。認証サーバへ遷移します (action=%s)", (gateway_form.get("action") or "")[:60])
        action = gateway_form.get("action") or ""
        post_url = urljoin(login_page_url, action) if action else login_page_url
        gateway_payload = {}
        for inp in gateway_form.find_all("input"):
            n = inp.get("name")
            if n and inp.get("type") != "submit":
                gateway_payload[n] = inp.get("value", "")
        try:
            r = session.post(post_url, data=gateway_payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            _wait_between_requests()
            soup = BeautifulSoup(r.text, "html.parser")
            login_page_url = r.url
            form = _get_form(soup)
        except requests.RequestException as e:
            logger.exception("[段階2] SSO ゲートウェイ POST に失敗: %s", e)
            return False

    if not form:
        logger.warning("[段階2] ログインフォームが見つかりません。最終 URL=%s", login_page_url)
        return False
    logger.info("[段階2] ログインページに到達しました (URL=%s)", login_page_url)

    logintoken = ""
    token_input = soup.find("input", {"name": "logintoken"})
    if token_input and token_input.get("value"):
        logintoken = token_input["value"]

    # フォームの action（POST 先）
    action = form.get("action") if form else ""
    post_url = urljoin(login_page_url, action) if action else login_page_url

    # フォーム内の全 input をベースに payload を構築（実際の name に合わせる）
    payload = {}
    user_field = None
    pass_field = None
    first_text_name = None
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        if inp.get("type") == "hidden":
            payload[name] = inp.get("value", "")
        elif inp.get("type") == "password":
            pass_field = name
        elif name == "logintoken":
            payload[name] = logintoken
        elif any(x in name.lower() for x in ("username", "user", "j_username", "email", "login", "eid", "uid", "omuid")):
            user_field = name
        elif inp.get("type") in ("text", "email", None) and first_text_name is None:
            first_text_name = name
    if user_field is None:
        user_field = first_text_name
    if user_field:
        payload[user_field] = MOODLE_USER
    if pass_field:
        payload[pass_field] = MOODLE_PASSWORD
    if "logintoken" not in payload and logintoken:
        payload["logintoken"] = logintoken

    logger.info("[段階3] ログインフォームに情報を打ち込み、送信します (POST先=%s)", post_url)
    try:
        r2 = session.post(post_url, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r2.raise_for_status()
        _wait_between_requests()
    except requests.RequestException as e:
        logger.exception("[段階3] ログイン送信に失敗しました: %s", e)
        return False

    # 2FA ページか確認（Moodle の 2段階認証）
    def _is_2fa_page(url: str, s: BeautifulSoup) -> bool:
        u = url.lower()
        if any(k in u for k in ("otp", "totp", "2fa", "verify", "mfa")):
            return True
        for inp in s.find_all("input", type=["text", "number"]):
            n = (inp.get("name") or inp.get("id") or "").lower()
            if any(k in n for k in ("code", "totp", "otp", "token", "verify", "pin")):
                return True
        return False

    def _find_totp_field(s: BeautifulSoup) -> Optional[str]:
        for inp in s.find_all("input", type=["text", "number"]):
            name = inp.get("name") or inp.get("id")
            if name and any(k in name.lower() for k in ("code", "totp", "otp", "token", "verify", "pin")):
                return name
        return None

    if _is_2fa_page(r2.url, BeautifulSoup(r2.text, "html.parser")) and TOTP_SECRET:
        soup2 = BeautifulSoup(r2.text, "html.parser")
        totp_field = _find_totp_field(soup2)
        if totp_field:
            code = pyotp.TOTP(TOTP_SECRET).now()
            logger.info("2FA コードを送信します")
            form2 = soup2.find("form")
            if form2:
                action2 = form2.get("action") or ""
                post_url2 = urljoin(r2.url, action2) if action2 else r2.url
                payload2 = {}
                for inp in form2.find_all("input"):
                    n = inp.get("name")
                    if n:
                        payload2[n] = code if n == totp_field else inp.get("value", "")
                if totp_field not in payload2:
                    payload2[totp_field] = code
                r3 = session.post(post_url2, data=payload2, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                r3.raise_for_status()
                _wait_between_requests()
                if _is_2fa_page(r3.url, BeautifulSoup(r3.text, "html.parser")):
                    logger.error("[段階4] 2FA 送信後も認証ページのまま。TOTP_SECRET を確認してください")
                    return False
                logger.info("[段階4] ログインに成功しました（2FA 完了）")
                return True
        logger.error("[段階4] 2FA フィールドが見つかりません。TOTP_SECRET は設定済みです")
        return False

    # ログイン失敗時はログインページに戻るか、エラーメッセージが含まれる
    if "login" in r2.url and "logintoken" in r2.text:
        logger.error("[段階4] ログインに失敗しました（ID/パスワードまたは logintoken を確認してください）")
        return False

    logger.info("[段階4] ログインに成功しました")
    return True


def login(session: requests.Session) -> bool:
    """Moodle に直接ログイン（2FA 対応）。"""
    return _login_direct(session)


def _is_sso_gateway_page(soup: BeautifulSoup) -> bool:
    """SSO ゲートウェイページか（hidden のみのフォームで auth へ POST）"""
    form = soup.find("form", action=re.compile(r"auth|AuthServer|MultiAuth", re.I))
    if not form:
        return False
    # SAML リダイレクト（GET で Moodle へ戻る）はゲートウェイではない
    if _is_saml_redirect_page(soup):
        return False
    has_user_or_pass = any(
        inp.get("type") in ("text", "password")
        or "user" in (inp.get("name") or "").lower()
        or "pass" in (inp.get("name") or "").lower()
        for inp in form.find_all("input")
    )
    return not has_user_or_pass


def _is_2fa_reauth_page(soup: BeautifulSoup) -> bool:
    """OMU 2FA 再認証ページか（SM_UID + SM_PWD のフォーム）"""
    form = soup.find("form", action=re.compile(r"SMAuthenticator", re.I))
    if not form:
        return False
    names = {inp.get("name") for inp in form.find_all("input") if inp.get("name")}
    return "SM_UID" in names and "SM_PWD" in names


def _is_saml_redirect_page(soup: BeautifulSoup) -> bool:
    """認証完了後の SAML リダイレクトページか（GET で Moodle へ戻る中間ページ）"""
    form = soup.find("form", action=re.compile(r"AuthnRequestReceiver|SamlIdP", re.I))
    if not form:
        return False
    if (form.get("method") or "get").lower() != "get":
        return False
    names = {inp.get("name") for inp in form.find_all("input") if inp.get("name")}
    return "SAMLRequest" in names and "RelayState" in names


def _follow_sso_gateways(session: requests.Session, html: str, current_url: str) -> tuple[str, str]:
    """
    SSO ゲートウェイ・2FA 再認証が続く限り POST して遷移し、最終 HTML と URL を返す。
    """
    soup = BeautifulSoup(html, "html.parser")
    for loop in range(8):
        is_2fa = _is_2fa_reauth_page(soup)
        is_gateway = _is_sso_gateway_page(soup)
        is_saml = _is_saml_redirect_page(soup)
        logger.info("[SSO判定] loop=%d url=%s is_2fa=%s is_gateway=%s is_saml=%s TOTP=%s", loop, current_url[:80], is_2fa, is_gateway, is_saml, bool(TOTP_SECRET))
        # 1) OMU 2FA 再認証を先に判定（smreload と totp が両方ある場合、totp を送る必要がある）
        if _is_2fa_reauth_page(soup) and TOTP_SECRET:
            form = soup.find("form", action=re.compile(r"SMAuthenticator", re.I))
            if not form:
                return html, current_url
            action = form.get("action") or ""
            post_url = urljoin(current_url, action) if action else current_url
            payload = {}
            for inp in form.find_all("input"):
                n = inp.get("name")
                if not n or inp.get("type") == "submit":
                    continue
                if n == "SM_UID":
                    payload[n] = MOODLE_USER
                elif n == "SM_PWD":
                    payload[n] = pyotp.TOTP(TOTP_SECRET).now()
                else:
                    payload[n] = inp.get("value", "")
            logger.info("[再認証] 2FA フォームを送信します")
            try:
                r = session.post(post_url, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                r.raise_for_status()
                _wait_between_requests()
                html = r.text
                current_url = r.url
                soup = BeautifulSoup(html, "html.parser")
            except requests.RequestException as e:
                logger.warning("[再認証] 2FA 送信に失敗: %s", e)
                return html, current_url
            continue
        # 2) 認証完了後の SAML リダイレクト（GET で Moodle へ戻る）
        elif _is_saml_redirect_page(soup):
            form = soup.find("form", action=re.compile(r"AuthnRequestReceiver|SamlIdP", re.I))
            if not form:
                return html, current_url
            action = form.get("action") or ""
            redirect_url = urljoin(current_url, action) if action else current_url
            params = {inp["name"]: inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            logger.info("[SSO判定] SAML リダイレクトを送信します (RelayState へ遷移)")
            try:
                r = session.get(redirect_url, params=params, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                r.raise_for_status()
                _wait_between_requests()
                html = r.text
                current_url = r.url
                soup = BeautifulSoup(html, "html.parser")
            except requests.RequestException as e:
                logger.warning("[SSO判定] SAML リダイレクト送信に失敗: %s", e)
                return html, current_url
            continue
        # 3) hidden のみのゲートウェイ
        elif _is_sso_gateway_page(soup):
            form = soup.find("form", action=re.compile(r"auth|AuthServer|MultiAuth", re.I))
            if not form:
                return html, current_url
        else:
            if is_2fa and not TOTP_SECRET:
                logger.warning("[SSO判定] 2FAページを検出しましたが TOTP_SECRET が未設定です。.env に TOTP_SECRET を追加してください")
            else:
                logger.info("[SSO判定] ゲートウェイ/2FA 以外のページのため終了")
            return html, current_url

        # ゲートウェイ（hidden のみ）の POST
        action = form.get("action") or ""
        post_url = urljoin(current_url, action) if action else current_url
        payload = {inp["name"]: inp.get("value", "") for inp in form.find_all("input") if inp.get("name") and inp.get("type") != "submit"}
        try:
            r = session.post(post_url, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            _wait_between_requests()
            html = r.text
            current_url = r.url
            soup = BeautifulSoup(html, "html.parser")
        except requests.RequestException:
            return html, current_url
    return html, current_url


def _parse_date(text: str) -> Optional[datetime]:
    """よくある日付文字列を datetime に変換。"""
    if not text or not text.strip():
        return None
    text = text.strip()
    # 例: "2025年2月15日 23:59", "15 February 2025, 11:59 PM", "2025-02-15 23:59"
    for fmt in (
        "%Y年%m月%d日 %H:%M",
        "%Y年%m月%d日",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d %B %Y, %I:%M %p",
        "%d %b %Y, %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _extract_assignments_from_calendar(session: requests.Session, base_url: str) -> List[Assignment]:
    """カレンダー「今後の予定」ページからイベント（課題含む）を抽出。"""
    base = base_url.rstrip("/")
    # 今後の予定ビュー（Moodle のバージョンでパスが少し違う場合あり）
    calendar_url = f"{base}/calendar/view.php?view=upcoming"
    try:
        r = session.get(calendar_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        _wait_between_requests()
    except requests.RequestException as e:
        logger.exception("カレンダーページの取得に失敗: %s", e)
        return []

    html, _ = _follow_sso_gateways(session, r.text, r.url)
    soup = BeautifulSoup(html, "html.parser")
    assignments: List[Assignment] = []

    # 授業一覧マップ
    course_map: dict[str, str] = {}
    course_select = soup.find("select", class_=re.compile(r"cal_courses_flt|calendar.*filter", re.I))
    if course_select:
        for opt in course_select.find_all("option", value=True):
            cid = opt.get("value", "").strip()
            cname = opt.get_text(strip=True)
            if cid and cid != "1" and cname and cname != "すべての授業科目":
                course_map[cid] = cname

    # Moodle のカレンダーは .event や [data-type="assign"] などでイベントを表示
    # 汎用的に「予定」らしいブロック」を探す
    event_containers = soup.find_all(class_=re.compile(r"event", re.I))
    if not event_containers:
        event_containers = soup.find_all("div", attrs={"data-type": re.compile(r"assign|assignment", re.I)})
    if not event_containers:
        # テーブル形式のカレンダー
        rows = soup.find_all("tr", class_=re.compile(r"event|calendar", re.I))
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            link = row.find("a", href=re.compile(r"mod/assign|assign/view|course/view"))
            if not link:
                continue
            title = link.get("title") or link.get_text(strip=True) or "（無題）"
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(base + "/", href)
            due_text = ""
            for c in cells:
                t = c.get_text(strip=True)
                if re.search(r"\d{4}[-/年]\d|due|締切|期限", t, re.I):
                    due_text = t
                    break
            due = _parse_date(due_text)
            assignments.append(Assignment(
                title=title,
                due_date=due,
                course_name="",
                url=href,
                description_preview="",
            ))
        return assignments

    for container in event_containers:
        link = container.find("a", href=re.compile(r"mod/assign|assign/view\.php"))
        if not link:
            continue
        title = link.get("title") or link.get_text(strip=True) or "（無題）"
        href = link.get("href", "")
        if not href.startswith("http"):
            href = urljoin(base + "/", href)
        # mod/assign のみ課題として扱う（quiz 等は除外）
        if "mod/assign" not in href:
            continue
        due = None
        date_elem = container.find(class_=re.compile(r"date|time|due"))
        if date_elem:
            due = _parse_date(date_elem.get_text())
        if not due:
            day_link = container.find_parent(["td", "div"], attrs={"data-day-timestamp": True})
            if day_link:
                ts = day_link.get("data-day-timestamp")
                if ts:
                    try:
                        due = datetime.fromtimestamp(int(ts))
                    except (ValueError, OSError):
                        pass
        if not due:
            full_text = container.get_text()
            for part in re.findall(r"[\d年/\-月日:\s]+", full_text):
                due = _parse_date(part)
                if due:
                    break
        course_name = ""
        for anc in container.parents:
            cid = anc.get("data-courseid")
            if cid and cid != "1" and cid in course_map:
                course_name = course_map[cid]
                break
        assignments.append(Assignment(
            title=title,
            due_date=due,
            course_name=course_name,
            url=href,
            description_preview="",
        ))

    return assignments


def _extract_assignments_from_my(session: requests.Session, base_url: str) -> List[Assignment]:
    """ダッシュボード（/my/）の「今後の課題」ブロックなどから抽出。"""
    base = base_url.rstrip("/")
    my_url = f"{base}/my/"
    try:
        r = session.get(my_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        _wait_between_requests()
    except requests.RequestException as e:
        logger.exception("マイページの取得に失敗: %s", e)
        return []

    html, _ = _follow_sso_gateways(session, r.text, r.url)
    soup = BeautifulSoup(html, "html.parser")
    assignments: List[Assignment] = []

    # カレンダーの授業一覧から course_id -> 授業名 のマップを構築
    course_map: dict[str, str] = {}
    course_select = soup.find("select", class_=re.compile(r"cal_courses_flt|calendar.*filter", re.I))
    if course_select:
        for opt in course_select.find_all("option", value=True):
            cid = opt.get("value", "").strip()
            cname = opt.get_text(strip=True)
            if cid and cid != "1" and cname and cname != "すべての授業科目":
                course_map[cid] = cname

    # 課題へのリンク（mod/assign/view.php を含む）
    for link in soup.find_all("a", href=re.compile(r"mod/assign/view\.php")):
        href = link.get("href", "")
        if not href.startswith("http"):
            href = urljoin(base + "/", href)
        title = link.get("title") or link.get_text(strip=True) or "（無題）"
        # 重複を避ける（同じ href は 1 回だけ）
        if any(a.url == href for a in assignments):
            continue
        # 親要素から日付・授業を探す
        due = None
        course_name = ""
        parent = link.find_parent(["li", "div", "tr", "td"])
        if parent:
            date_elem = parent.find(class_=re.compile(r"date|time|due|deadline"))
            if date_elem:
                due = _parse_date(date_elem.get_text())
            if not due:
                for t in re.findall(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[^\d]*\d{1,2}:\d{2}", parent.get_text()):
                    due = _parse_date(t)
                    if due:
                        break
            # data-day-timestamp から日付を取得（カレンダー月表示）
            if not due:
                day_link = parent.find("a", attrs={"data-timestamp": True})
                if day_link:
                    ts = day_link.get("data-timestamp")
                    if ts:
                        try:
                            from datetime import datetime as dt
                            due = dt.fromtimestamp(int(ts))
                        except (ValueError, OSError):
                            pass
            # 親の data-courseid から授業名を取得
            for anc in parent.parents:
                cid = anc.get("data-courseid") or anc.get("data-course-id")
                if cid and cid != "1" and cid in course_map:
                    course_name = course_map[cid]
                    break
                # calendar/view.php?course=XXX のリンクから授業を取得
                for a in anc.find_all("a", href=re.compile(r"course=\d+")):
                    m = re.search(r"course=(\d+)", a.get("href", ""))
                    if m and m.group(1) in course_map:
                        course_name = course_map[m.group(1)]
                        break
                if course_name:
                    break
        assignments.append(Assignment(
            title=title,
            due_date=due,
            course_name=course_name,
            url=href,
            description_preview="",
        ))

    return assignments


def fetch_assignments() -> List[Assignment]:
    """
    ログインして課題一覧を取得する。
    カレンダーとダッシュボードの両方から取得し、重複を除いて返す。
    """
    session = _session()
    if not login(session):
        return []

    base = MOODLE_URL.rstrip("/")
    seen_urls: set[str] = set()
    result: List[Assignment] = []

    for assign in _extract_assignments_from_calendar(session, base) + _extract_assignments_from_my(session, base):
        # 同一 URL は 1 件だけ
        norm_url = assign.url.split("?")[0]
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)
        result.append(assign)

    # 締切日でソート（None は後ろ）
    result.sort(key=lambda a: (a.due_date is None, a.due_date or datetime.max))
    return result
