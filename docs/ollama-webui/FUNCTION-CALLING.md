# Open WebUI から ローカルLLM に Function Calling させる（詰まった時の切り分け）

Playwright API は動くのに、チャットから get_title が呼ばれない。
その状態を潰すための手順である。上から順にやること。

## 前提として知っておくこと

ブラウザの DevTools で見えるチャット送信 Payload に `tools` が無いのは正常である。
ブラウザが送るのは有効化したツールの識別子だけ。

- Workspace Tools → `tool_ids`
- 外部 OpenAPI サーバ → `tool_servers`

実際の JSON Schema は Open WebUI のバックエンドが組み立て、Ollama へのリクエストに載せる。
つまり検証すべきは ブラウザ→OpenWebUI ではなく OpenWebUI→Ollama の通信である。

## 手順1. Function Calling を Native にする（最重要）

Open WebUI の Function Calling には2方式ある。

- Default … プロンプト方式。ツール説明を文章で埋め込み、返答から JSON を拾う。小型モデルだと頻繁に失敗し、思考文だけで終わる
- Native … Ollama の tools API をそのまま使う。モデルが学習済みの tool call 形式で返す

チャット右上の Controls パネル → Advanced Params → Function Calling を Native に変更する。
毎回設定したくないなら Workspace → Models からモデルを編集し、既定値を Native にしておく。

## 手順2. モデルが tools に対応しているか確認

```powershell
docker exec -it ollama ollama show qwen3:8b
```

Capabilities に tools が含まれていること。含まれないモデルは Native にしても呼べない。

## 手順3. Ollama に tools が届いているかログで確認する

Ollama にはリクエストボディを吐く環境変数がある。compose.yml の ollama サービスに足す。

```yaml
    environment:
      - OLLAMA_DEBUG=1
      - OLLAMA_DEBUG_LOG_REQUESTS=true
```

Open WebUI 側も喋らせる。

```yaml
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - GLOBAL_LOG_LEVEL=DEBUG
```

再起動してログを流したままチャットを送る。

```powershell
docker compose -f compose.yml -f compose.gpu.yml up -d
docker compose logs -f ollama
```

判定はこうなる。

- `"tools":[{"type":"function","function":{"name":"get_title"` が出る → 経路は正常。以降はモデル側の問題
- 出ない → Open WebUI が送っていない。手順1に戻る（Native になっていない、ツールがオンになっていない）

確認が済んだら OLLAMA_DEBUG_LOG_REQUESTS は false に戻すこと。ログが爆発する。

## 手順4. Thinking を切る

Qwen3 の Thinking は tool calling と相性が悪く、思考の中で「呼ぶべきだ」と結論して満足し、
実際の呼び出しを出さずに終わることがある。

- メッセージ末尾かシステムプロンプトに `/no_think` を入れる
- 切り分け中は Thinking の無い qwen2.5:7b-instruct で先に成功させる

モデル自身が Thinking をオフにできないと答えても、それはモデルが自分の設定を知らないだけである。

## 手順5. Tool のコードを仕様に合わせる

Open WebUI は 型ヒント と docstring から JSON Schema を生成する。
docstring が無いと description が空になり、モデルには名前しか見えない。何をする関数か分からなければ呼ばれない。

正しい形は tools/playwright_tool.py を参照。要点は3つ。

1. 引数と戻り値に型ヒントを付ける
2. docstring に「何をする関数か」と `:param url:` を書く
3. 推測で答えず必ず呼べ、と docstring 自体に明記する

## 外部 OpenAPI Tool Server を使う場合のURL

登録する URL は末尾に /openapi.json を付けない。ベースURLだけを書く。
さらに、誰がその URL を取りに行くかで正解が変わる。

- ユーザー設定の Settings → Tools に登録 … ブラウザが取得するので `http://localhost:8000`
- 管理画面の Admin Panel → Settings → Tools に登録 … バックエンドが取得するので `http://playwright:8000`

コンテナから見た localhost は自分自身を指す。ここを取り違えると接続テストは通るのに実行時に落ちる。

## それでも呼ばれない時

- ツールが多すぎる。まず get_title 1つだけにして検証する
- 指示が曖昧。まずは「get_title を使って https://example.com のタイトルを取得して」と明示的に命令して経路を通す
- コンテキスト長不足。ツール定義もトークンを食う。num_ctx を 8192 程度に上げる
