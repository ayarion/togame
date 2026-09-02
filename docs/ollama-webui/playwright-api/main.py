"""
LLM から呼び出すためのブラウザ操作 API

エンドポイントは2系統ある。

読み取り系 (/title, /text, /links, /screenshot)
    1リクエストで完結する。毎回まっさらなタブを開いて、終わったら閉じる。
    ページを見るだけの用途はこちら。

セッション操作系 (/session/*)
    1枚のタブを開いたまま保持し、クリックや入力を積み重ねる。
    検索してから結果を開く、ログインしてから中を見る、のような
    複数手順の操作はこちらでないとできない。

どのエンドポイントも HTTP 200 で {"ok": true/false} を返す。
失敗をエラーコードではなく本文で返すのは、LLM が結果を読んで
次の手を考えられるようにするためである。
"""

import asyncio
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

SHOT_DIR = Path(os.environ.get("SHOT_DIR", "/data/shots"))
# スクリーンショットのURLを組み立てる時の外向きのベース。ブラウザから見えるアドレスを入れる
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
TIMEOUT_MS = int(os.environ.get("TIMEOUT_MS", "30000"))

_pw = None
_browser = None
_session_context = None
_session_page = None
# セッションは1枚のタブを共有するので、同時に触られないよう直列化する
_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pw, _browser
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    _pw = await async_playwright().start()
    _browser = await _pw.chromium.launch(
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    yield
    if _browser:
        await _browser.close()
    if _pw:
        await _pw.stop()


app = FastAPI(
    title="Browser Tools API",
    description="LLM から呼び出すためのブラウザ操作API",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------- 共通処理


def _clean(text: str, limit: int) -> str:
    """LLM に渡す前に空白を潰して長さを切る。文脈を食い潰さないための処理である"""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        return text[:limit] + f"\n...(以下略 全{len(text)}文字)"
    return text


def _normalize(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


@asynccontextmanager
async def _temp_page():
    """読み取り系で使う使い捨てのタブ"""
    context = await _browser.new_context(viewport={"width": 1280, "height": 900})
    page = await context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    try:
        yield page
    finally:
        await context.close()


async def _snapshot(page, excerpt: int = 800) -> dict:
    """今ページがどうなっているかを返す。操作のたびにこれを返すと LLM が次の手を判断できる"""
    try:
        body = await page.inner_text("body")
    except Exception:
        body = ""
    return {
        "url": page.url,
        "title": await page.title(),
        "text_excerpt": _clean(body, excerpt),
    }


async def _require_session() -> dict | None:
    if _session_page is None or _session_page.is_closed():
        return {"ok": False, "error": "ページがまだ開かれていない。先に /session/open を呼ぶこと"}
    return None


# ---------------------------------------------------------------- 読み取り系


@app.get("/title", summary="ページのタイトルを取得する")
async def get_title(url: str):
    try:
        async with _temp_page() as page:
            await page.goto(_normalize(url), wait_until="domcontentloaded")
            return {"ok": True, "url": page.url, "title": await page.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/text", summary="ページ本文のテキストを取得する")
async def get_text(url: str, max_chars: int = 3000):
    try:
        async with _temp_page() as page:
            await page.goto(_normalize(url), wait_until="domcontentloaded")
            # script や style は本文ではないので落としてから取る
            await page.evaluate(
                "document.querySelectorAll('script,style,noscript').forEach(e => e.remove())"
            )
            body = await page.inner_text("body")
            return {
                "ok": True,
                "url": page.url,
                "title": await page.title(),
                "text": _clean(body, max_chars),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/links", summary="ページ内のリンク一覧を取得する")
async def get_links(url: str, limit: int = 30):
    try:
        async with _temp_page() as page:
            await page.goto(_normalize(url), wait_until="domcontentloaded")
            links = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({ text: a.innerText.trim().slice(0, 80), href: a.href }))
                    .filter(l => l.text && l.href.startsWith('http'))"""
            )
            seen, unique = set(), []
            for link in links:
                if link["href"] in seen:
                    continue
                seen.add(link["href"])
                unique.append(link)
                if len(unique) >= limit:
                    break
            return {"ok": True, "url": page.url, "count": len(unique), "links": unique}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/screenshot", summary="ページのスクリーンショットを撮る")
async def screenshot(url: str, full_page: bool = False):
    try:
        async with _temp_page() as page:
            await page.goto(_normalize(url), wait_until="networkidle")
            name = f"{uuid.uuid4().hex}.png"
            await page.screenshot(path=str(SHOT_DIR / name), full_page=full_page)
            return {
                "ok": True,
                "url": page.url,
                "title": await page.title(),
                "image_url": f"{PUBLIC_BASE_URL}/shots/{name}",
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/shots/{name}", include_in_schema=False)
async def serve_shot(name: str):
    # パス遡りを防ぐため、UUID + .png の形だけを通す
    if not re.fullmatch(r"[0-9a-f]{32}\.png", name):
        return {"ok": False, "error": "invalid name"}
    path = SHOT_DIR / name
    if not path.exists():
        return {"ok": False, "error": "not found"}
    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------- セッション操作系


class OpenBody(BaseModel):
    url: str = Field(description="開くページの完全なURL")


class ClickBody(BaseModel):
    text: str = Field(description="クリックしたいボタンやリンクの表示文字列")


class FillBody(BaseModel):
    field: str = Field(description="入力欄のラベル、プレースホルダ、またはCSSセレクタ")
    value: str = Field(description="入力する文字列")


class PressBody(BaseModel):
    key: str = Field(default="Enter", description="押すキー。Enter, Tab, Escape など")


@app.post("/session/open", summary="ブラウザでページを開いて保持する")
async def session_open(body: OpenBody):
    global _session_context, _session_page
    async with _lock:
        try:
            if _session_context is not None:
                await _session_context.close()
            _session_context = await _browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            _session_page = await _session_context.new_page()
            _session_page.set_default_timeout(TIMEOUT_MS)
            await _session_page.goto(_normalize(body.url), wait_until="domcontentloaded")
            return {"ok": True, **await _snapshot(_session_page)}
        except Exception as e:
            return {"ok": False, "error": str(e)}


@app.post("/session/click", summary="開いているページ上の要素をクリックする")
async def session_click(body: ClickBody):
    async with _lock:
        if err := await _require_session():
            return err
        page = _session_page
        # LLM は CSS セレクタを間違えるので、表示文字列から順に探す
        candidates = [
            page.get_by_role("button", name=body.text),
            page.get_by_role("link", name=body.text),
            page.get_by_text(body.text, exact=False),
        ]
        for locator in candidates:
            try:
                await locator.first.click(timeout=5000)
                await page.wait_for_load_state("domcontentloaded")
                return {"ok": True, "clicked": body.text, **await _snapshot(page)}
            except Exception:
                continue
        return {"ok": False, "error": f"{body.text} という要素が見つからなかった"}


@app.post("/session/fill", summary="開いているページの入力欄に文字を入れる")
async def session_fill(body: FillBody):
    async with _lock:
        if err := await _require_session():
            return err
        page = _session_page
        candidates = [
            page.get_by_label(body.field),
            page.get_by_placeholder(body.field),
            page.locator(body.field),
        ]
        for locator in candidates:
            try:
                await locator.first.fill(body.value, timeout=5000)
                return {"ok": True, "filled": body.field, **await _snapshot(page)}
            except Exception:
                continue
        return {"ok": False, "error": f"{body.field} という入力欄が見つからなかった"}


@app.post("/session/press", summary="開いているページでキーを押す")
async def session_press(body: PressBody):
    async with _lock:
        if err := await _require_session():
            return err
        try:
            await _session_page.keyboard.press(body.key)
            await _session_page.wait_for_load_state("domcontentloaded")
            return {"ok": True, "pressed": body.key, **await _snapshot(_session_page)}
        except Exception as e:
            return {"ok": False, "error": str(e)}


@app.get("/session/state", summary="今開いているページの状態を取得する")
async def session_state(max_chars: int = 2000):
    if err := await _require_session():
        return err
    return {"ok": True, **await _snapshot(_session_page, excerpt=max_chars)}


@app.get("/session/screenshot", summary="今開いているページのスクリーンショットを撮る")
async def session_screenshot(full_page: bool = False):
    async with _lock:
        if err := await _require_session():
            return err
        try:
            name = f"{uuid.uuid4().hex}.png"
            await _session_page.screenshot(path=str(SHOT_DIR / name), full_page=full_page)
            return {
                "ok": True,
                "url": _session_page.url,
                "image_url": f"{PUBLIC_BASE_URL}/shots/{name}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


@app.post("/session/close", summary="開いているページを閉じる")
async def session_close():
    global _session_context, _session_page
    async with _lock:
        if _session_context is not None:
            await _session_context.close()
        _session_context = None
        _session_page = None
        return {"ok": True, "message": "closed"}
