# Ollama × Open WebUI をDockerで立てる（初心者向け・全手順）

自分のPCの中だけでLLMを動かし、ChatGPTみたいなチャット画面から使えるようにする手順である。
外部にデータが出ないので、雑なメモでも個人情報でも気兼ねなく投げられるのが最大の利点。

## 0. 用語を先に3つだけ

- Ollama … モデル本体を動かすエンジン。画面は持たず、ポート11434でAPIを喋るだけの裏方
- Open WebUI … ブラウザで使うチャット画面。裏でOllamaに問い合わせている
- Docker … この2つを、PCを汚さずに箱の中で動かす仕組み

つまり作るのは、画面（Open WebUI）→ エンジン（Ollama）→ モデルファイル、の3階建てである。

## 1. Dockerを入れる

- Windows / Mac … Docker Desktop を公式サイトからインストール
- Linux … Docker Engine と Docker Compose プラグインをインストール

入ったかの確認。バージョンが2つとも表示されればOK。

```bash
docker --version
docker compose version
```

Windowsの人はDocker Desktopの設定でWSL2が有効になっていること。ここが未設定だと後で必ず詰まる。

## 2. 置き場所を作ってファイルを置く

このフォルダの compose.yml をそのまま使う。好きな場所にフォルダを作り、compose.yml を置くだけでよい。

```bash
mkdir -p ~/ollama-webui && cd ~/ollama-webui
# ここに compose.yml をコピーする
```

## 3. 起動する

```bash
docker compose up -d
```

初回はイメージのダウンロードで数分かかる。-d はバックグラウンド起動の意味。

状態確認。ollama と open-webui の2つが Up になっていれば成功である。

```bash
docker compose ps
```

## 4. 画面を開いて最初のアカウントを作る

ブラウザで http://localhost:3000 を開く。

サインアップ画面が出るので、名前・メール・パスワードを入れて登録する。
このメールアドレスは外部に送信されず、コンテナの中のDBに保存されるだけ。
そして最初に登録した人が自動で管理者になる。あとから来た人は一般ユーザーになる。

パスワードを忘れると面倒なので、ここは真面目にメモしておくこと。

## 5. モデルを入れる

まだ頭脳が空っぽなのでモデルを落とす。方法は2つある。

方法A（画面から）
右上の設定 → 管理者設定 → モデル → モデル名を入力してダウンロード。

方法B（コマンドから。こちらが確実）

```bash
docker compose exec ollama ollama pull gemma3:4b
```

最初の1つの選び方の目安。

- メモリ8GB前後 … gemma3:4b, llama3.2:3b, qwen3:4b あたり
- メモリ16GB … gemma3:12b, qwen3:8b
- メモリ32GB以上かGPUあり … gpt-oss:20b, qwen3:14b 以上も狙える

日本語の自然さ重視なら gemma3 か qwen3 系が扱いやすい。
迷ったら小さいのから始めること。いきなり大きいモデルを引いてPCが固まるのが初心者の定番の事故である。

入っているモデルの一覧。

```bash
docker compose exec ollama ollama list
```

## 6. 使う

http://localhost:3000 に戻り、左上のモデル選択でさっき落としたモデルを選んで話しかける。
返事が返ってきたら完成である。ここまでで完全にオフラインで動く自分専用AIができている。

## GPUを使う場合（NVIDIA）

CPUだけでも動くが遅い。NVIDIAのGPUがあるなら使ったほうが体感が10倍変わる。

1. GPUドライバを入れる
2. NVIDIA Container Toolkit を入れる（WindowsはWSL2側に）
3. 確認する

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

4. GPU設定を足して起動する

```bash
docker compose -f compose.yml -f compose.gpu.yml up -d
```

効いているかは、生成中に別ターミナルで nvidia-smi を叩いてollamaがGPUメモリを掴んでいるかで判断する。

## Macの場合は要注意

Apple SiliconのMacでは、Dockerコンテナの中からMacのGPU（Metal）を使えない。
つまりDocker版Ollamaを使うとCPUのみで動き、びっくりするほど遅い。

なのでMacでは構成を変える。Ollama本体はMacに直接インストールし、WebUIだけDockerで動かす。

```bash
brew install ollama
ollama serve            # 別ターミナルで起動しっぱなしにする
ollama pull gemma3:4b
docker compose -f compose.mac.yml up -d
```

これで http://localhost:3000 から、Macのフルスピードで動くOllamaに繋がる。

## よく使うコマンド

```bash
docker compose logs -f open-webui   # ログを見る
docker compose restart              # 再起動
docker compose stop                 # 停止（データは残る）
docker compose up -d                # 再開
docker compose pull && docker compose up -d   # 最新版に更新
docker compose down                 # 停止して削除（volumeは残るのでデータは無事）
docker compose down -v              # volumeごと消す。モデルも会話履歴も全部消えるので注意
```

## つまずきポイントと対処

画面が開かない
- docker compose ps でopen-webuiがUpか確認する。Exitedならlogsを見る
- 3000番が他のアプリと衝突している場合は compose.yml の "3000:8080" を "3100:8080" などに変える

WebUIは開くがモデルが1つも出てこない
- Ollama側にモデルが無い。手順5のpullをやる
- それでも駄目ならWebUIからOllamaに届いていない。OLLAMA_BASE_URL が http://ollama:11434 になっているか確認する。localhost:11434 と書くのは間違いで、コンテナから見たlocalhostは自分自身を指してしまう

返事が出るまでが異常に遅い
- モデルがPCのメモリに対して大きすぎる。1つ下のサイズに落とす
- GPUが認識されていない。上のGPU確認手順をやり直す

途中で落ちる、応答が止まる
- メモリ不足の可能性が高い。Docker Desktopの設定でメモリ割当を増やすか、小さいモデルにする

Linuxで host.docker.internal が解決できない
- compose に extra_hosts で host.docker.internal:host-gateway を足す

## 安全のための一言

11434番も3000番も、そのまま外向きに公開しないこと。
このcompose.ymlでOllamaを 127.0.0.1 に縛っているのはそのためである。
外から使いたくなったら、ポート開放ではなくVPNやトンネル経由にすること。認証なしのOllamaを世界に晒すのは、玄関の鍵を開けて旅行に出るのと同じである。

## データはどこにあるか

- モデル本体 … ollama volume（コンテナ内 /root/.ollama）
- 会話履歴やアカウント … open-webui volume（コンテナ内 /app/backend/data）

docker volume ls で見える。down -v をしない限り消えない。
