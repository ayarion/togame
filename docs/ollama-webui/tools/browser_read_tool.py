"""
title: Browser Read
author: ayarion
version: 1.0.0
description: ページを見るだけの読み取り系ツール。Open WebUI の Workspace Tools に貼り付けて使う。

docstring と型ヒントから JSON Schema が作られる。
docstring を消すとモデルに説明が届かず、関数は呼ばれなくなる。必ず残すこと。
"""

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        api_base: str = Field(
            default="http://playwright:8000",
            description="ブラウザ操作APIのベースURL。同じDockerネットワーク内なのでサービス名で解決する",
        )
        timeout: int = Field(default=60, description="1リクエストのタイムアウト秒")

    def __init__(self):
        self.valves = self.Valves()
        self.citation = True

    def _get(self, path: str, params: dict) -> dict:
        r = requests.get(
            f"{self.valves.api_base}{path}",
            params=params,
            timeout=self.valves.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_page_title(self, url: str) -> str:
        """
        実際のブラウザで指定URLを開き、そのページのタイトルを取得して返す。
        記憶や推測で答えてはならず、URLのタイトルを問われたら必ずこの関数を呼ぶこと。

        :param url: 開く対象の完全なURL。例 https://example.com
        :return: ページタイトルの文字列。
        """
        try:
            data = self._get("/title", {"url": url})
            if not data.get("ok"):
                return f"取得に失敗した: {data.get('error')}"
            return data["title"]
        except Exception as e:
            return f"取得に失敗した: {e}"

    def get_page_text(self, url: str, max_chars: int = 3000) -> str:
        """
        実際のブラウザで指定URLを開き、そのページの本文テキストを取得して返す。
        ページの内容を要約する、書いてあることを答える、といった依頼では必ずこの関数を呼ぶこと。

        :param url: 開く対象の完全なURL。
        :param max_chars: 取得する本文の最大文字数。既定は3000。
        :return: ページのタイトルと本文テキスト。
        """
        try:
            data = self._get("/text", {"url": url, "max_chars": max_chars})
            if not data.get("ok"):
                return f"取得に失敗した: {data.get('error')}"
            return f"タイトル: {data['title']}\n\n{data['text']}"
        except Exception as e:
            return f"取得に失敗した: {e}"

    def get_page_links(self, url: str, limit: int = 30) -> str:
        """
        実際のブラウザで指定URLを開き、そのページに含まれるリンクの一覧を取得して返す。
        このページから何が辿れるか、どんなリンクがあるか、を問われたら必ずこの関数を呼ぶこと。

        :param url: 開く対象の完全なURL。
        :param limit: 取得するリンクの最大件数。既定は30。
        :return: リンクの表示文字列とURLの一覧。
        """
        try:
            data = self._get("/links", {"url": url, "limit": limit})
            if not data.get("ok"):
                return f"取得に失敗した: {data.get('error')}"
            lines = [f"- {l['text']} -> {l['href']}" for l in data["links"]]
            return f"{data['count']}件のリンク\n" + "\n".join(lines)
        except Exception as e:
            return f"取得に失敗した: {e}"

    def take_screenshot(self, url: str, full_page: bool = False) -> str:
        """
        実際のブラウザで指定URLを開き、その見た目のスクリーンショットを撮って返す。
        見た目を確認したい、どんなデザインか、と問われたら必ずこの関数を呼ぶこと。
        戻り値に含まれる画像のMarkdown記法は、そのまま改変せずに回答に含めること。

        :param url: 開く対象の完全なURL。
        :param full_page: Trueならページ全体、Falseなら表示範囲のみ。既定はFalse。
        :return: 画像を表示するMarkdown記法を含む文字列。
        """
        try:
            data = self._get("/screenshot", {"url": url, "full_page": full_page})
            if not data.get("ok"):
                return f"撮影に失敗した: {data.get('error')}"
            return f"![screenshot]({data['image_url']})"
        except Exception as e:
            return f"撮影に失敗した: {e}"
