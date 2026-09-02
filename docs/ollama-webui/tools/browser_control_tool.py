"""
title: Browser Control
author: ayarion
version: 1.0.0
description: ページを開いたまま操作する系のツール。クリックや入力を積み重ねられる。

読み取り系(Browser Read)と同時にオンにすると、8Bクラスのモデルには選択肢が多すぎて迷う。
まずはどちらか一方だけを有効にして検証すること。
"""

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        api_base: str = Field(
            default="http://playwright:8000",
            description="ブラウザ操作APIのベースURL",
        )
        timeout: int = Field(default=60, description="1リクエストのタイムアウト秒")

    def __init__(self):
        self.valves = self.Valves()
        self.citation = True

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(
            f"{self.valves.api_base}{path}",
            json=body,
            timeout=self.valves.timeout,
        )
        r.raise_for_status()
        return r.json()

    def _format(self, data: dict) -> str:
        if not data.get("ok"):
            return f"操作に失敗した: {data.get('error')}"
        return (
            f"現在のURL: {data.get('url')}\n"
            f"タイトル: {data.get('title')}\n\n"
            f"{data.get('text_excerpt', '')}"
        )

    def open_page(self, url: str) -> str:
        """
        ブラウザで指定URLを開き、そのタブを開いたまま保持する。
        クリックや入力を伴う操作の起点となる関数であり、他の操作の前に必ず最初に呼ぶこと。

        :param url: 開く対象の完全なURL。例 https://example.com
        :return: 開いたページのURL、タイトル、本文の冒頭。
        """
        try:
            return self._format(self._post("/session/open", {"url": url}))
        except Exception as e:
            return f"操作に失敗した: {e}"

    def click_text(self, text: str) -> str:
        """
        今開いているページ上で、指定した文字列を持つボタンやリンクをクリックする。
        CSSセレクタではなく、画面に見えている表示文字列をそのまま渡すこと。
        事前に open_page でページを開いておく必要がある。

        :param text: クリックしたいボタンやリンクの表示文字列。例 ログイン
        :return: クリック後のページのURL、タイトル、本文の冒頭。
        """
        try:
            return self._format(self._post("/session/click", {"text": text}))
        except Exception as e:
            return f"操作に失敗した: {e}"

    def fill_field(self, field: str, value: str) -> str:
        """
        今開いているページの入力欄に文字を入力する。
        入力欄はラベル名かプレースホルダの文字列で指定する。
        事前に open_page でページを開いておく必要がある。

        :param field: 入力欄のラベルまたはプレースホルダの文字列。例 メールアドレス
        :param value: 入力する文字列。
        :return: 入力後のページのURL、タイトル、本文の冒頭。
        """
        try:
            return self._format(self._post("/session/fill", {"field": field, "value": value}))
        except Exception as e:
            return f"操作に失敗した: {e}"

    def press_key(self, key: str = "Enter") -> str:
        """
        今開いているページでキーボードのキーを押す。検索欄で確定する時などに使う。
        事前に open_page でページを開いておく必要がある。

        :param key: 押すキーの名前。Enter, Tab, Escape など。既定は Enter。
        :return: キー入力後のページのURL、タイトル、本文の冒頭。
        """
        try:
            return self._format(self._post("/session/press", {"key": key}))
        except Exception as e:
            return f"操作に失敗した: {e}"

    def get_current_page(self, max_chars: int = 2000) -> str:
        """
        今開いているページの現在の状態を取得する。
        操作の結果を確認したい時や、今どこにいるか分からなくなった時に呼ぶこと。

        :param max_chars: 取得する本文の最大文字数。既定は2000。
        :return: 現在のURL、タイトル、本文。
        """
        try:
            r = requests.get(
                f"{self.valves.api_base}/session/state",
                params={"max_chars": max_chars},
                timeout=self.valves.timeout,
            )
            r.raise_for_status()
            return self._format(r.json())
        except Exception as e:
            return f"取得に失敗した: {e}"
