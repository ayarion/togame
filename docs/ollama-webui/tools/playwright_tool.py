"""
title: Playwright Web Tools
author: ayarion
version: 0.1.0
required_open_webui_version: 0.5.0
description: Open WebUI の Workspace Tools に貼り付けて使う。Playwright FastAPI 経由で実ページを開く。

Open WebUI は「型ヒント」と「docstring」から JSON Schema を生成する。
docstring が無いと description が空になり、モデルは何をする関数か分からず呼ばない。
:param 行まで含めて必ず書くこと。
"""

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        api_base: str = Field(
            default="http://playwright:8000",
            description="Playwright FastAPI のベースURL。同じ Docker ネットワーク内なのでサービス名で解決する",
        )
        timeout: int = Field(
            default=60,
            description="1リクエストのタイムアウト秒。実ブラウザ起動があるので短くしすぎない",
        )

    def __init__(self):
        self.valves = self.Valves()
        # 引用のたびにソースを出したくない場合は False
        self.citation = True

    def get_title(self, url: str) -> str:
        """
        実際のブラウザで指定URLのWebページを開き、そのページのタイトル(HTMLの<title>)を取得して返す。
        推測や記憶で答えてはならず、URLのタイトルを問われたら必ずこの関数を呼ぶこと。

        :param url: 開く対象の完全なURL。例 https://example.com
        :return: 取得したページタイトルの文字列。失敗した場合はエラー内容の文字列。
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            response = requests.get(
                f"{self.valves.api_base}/title",
                params={"url": url},
                timeout=self.valves.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("title", "No title found")
        except Exception as e:
            return f"Failed to get page title: {e}"
