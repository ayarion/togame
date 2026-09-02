# ブラウザ操作ツールを足す

get_title 1個で通した経路に、実際にページを操作できる関数を追加する手順である。

## 何が増えるのか

読み取り系（Browser Read）… 1リクエストで完結する。使い捨てのタブを開いて閉じる

| 関数 | できること |
| --- | --- |
| get_page_title | ページのタイトルを取る |
| get_page_text | ページの本文テキストを取る |
| get_page_links | ページ内のリンク一覧を取る |
| take_screenshot | 見た目のスクリーンショットを撮る |

操作系（Browser Control）… タブを開いたまま保持し、操作を積み重ねる

| 関数 | できること |
| --- | --- |
| open_page | ページを開いて保持する。操作の起点 |
| click_text | 表示文字列でボタンやリンクをクリックする |
| fill_field | ラベル名で入力欄に文字を入れる |
| press_key | Enter などのキーを押す |
| get_current_page | 今の状態を確認する |

操作系が別物なのは、状態を持つからである。読み取り系は毎回タブを捨てるので、
クリックしてから中を見る、という手順が成立しない。

## 設計上の判断を2つ

LLM にクリック対象を CSS セレクタで指定させると、まず当たらない。
だから click_text は画面に見えている表示文字列で探す。
内部では ボタン → リンク → 任意のテキスト の順に候補を試している。

操作系の関数はどれも、実行後に必ず 現在のURL、タイトル、本文の冒頭 を返す。
自分の操作が何を起こしたかをモデルが読めないと、次の手を決められないためである。

## 導入手順

### 1. API を差し替える

playwright-api/ の main.py, Dockerfile, requirements.txt を配置する。
Dockerfile のベースイメージのバージョンと requirements.txt の playwright の
バージョンは必ず一致させること。ずれると Executable doesn't exist で起動しない。

```powershell
docker compose -f compose.yml -f compose.gpu.yml -f compose.playwright.yml up -d --build
```

### 2. API 単体で動作確認する

Open WebUI を挟む前に、API だけで確かめる。ここを飛ばすと切り分けができなくなる。

```powershell
curl.exe "http://localhost:8000/title?url=https://example.com"
curl.exe "http://localhost:8000/text?url=https://example.com&max_chars=500"
curl.exe "http://localhost:8000/links?url=https://example.com"
curl.exe "http://localhost:8000/screenshot?url=https://example.com"
```

セッション操作系も確認する。

```powershell
curl.exe -X POST http://localhost:8000/session/open -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\"}"
curl.exe -X POST http://localhost:8000/session/click -H "Content-Type: application/json" -d "{\"text\":\"More information\"}"
curl.exe http://localhost:8000/session/state
```

### 3. Open WebUI にツールを登録する

ワークスペース → ツール で2つ作る。

- tools/browser_read_tool.py の中身を貼って保存
- tools/browser_control_tool.py の中身を貼って保存

### 4. モデルに紐付ける

ワークスペース → モデル で編集し、ツール欄で どちらか一方 を選ぶ。

8Bクラスに9個の関数を渡すと確実に迷う。まず読み取り系だけで通し、
安定したら操作系に切り替える。両方同時にオンにするのは最後でよい。

組み込みツールは全部オフのままにしておくこと。

### 5. 試す

読み取り系

```
https://example.com の本文を要約して
https://example.com にどんなリンクがあるか教えて
https://example.com のスクリーンショットを見せて
```

操作系

```
https://example.com を開いて、More information をクリックして、そのページのタイトルを教えて
```

操作系が通れば、モデルが自分で複数手順を組み立てて実行している。
ここまで来ると、単なるツール呼び出しではなくエージェントの入口である。

## 注意しておくこと

セッションは1枚のタブを共有している。同時に2つの会話から操作すると混ざる。
個人利用なら問題ないが、複数人で使うならセッションIDを持たせる改修が要る。

このAPIは渡されたURLをそのまま開く。社内ネットワークや localhost にも到達できるため、
外部に公開してはならない。compose では 127.0.0.1 に縛ってある。

スクリーンショットは shots ボリュームに溜まり続ける。容量が気になったら
`docker compose down -v` ではなく、コンテナ内の /data/shots を掃除すること。

失敗した時は BROWSER の前に FUNCTION-CALLING.md を見ること。
ツールが呼ばれない原因の大半は Native 設定かツールの数である。
