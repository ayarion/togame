/* トガメのエージェント用プロキシ。
   APIキーは静的HTMLに置けない（GitHub Pagesは世界中から読める）ので、
   Cloudflare Workers を1枚だけ挟んでキーをこちら側に隠す。

   デプロイ:
     npx wrangler secret put ANTHROPIC_API_KEY   # Anthropicのコンソールで発行したキー
     npx wrangler secret put TOGAME_SECRET       # 自分で決める合言葉。トガメの設定にも同じものを入れる
     npx wrangler deploy

   合言葉は、このWorkerを他人に勝手に使われて課金が伸びるのを防ぐためだけのもの。 */

const MODEL = "claude-opus-5";

/* ここに載っていないオリジンからは叩けない */
const ALLOWED_ORIGINS = [
  "https://tsukuriba.org",
  "http://localhost:8123",   // ローカル検証用
];

function corsHeaders(origin){
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "access-control-allow-origin": allow,
    "access-control-allow-headers": "content-type,x-togame-key",
    "access-control-allow-methods": "POST,OPTIONS",
    "vary": "origin",
  };
}

export default {
  async fetch(req, env){
    const h = corsHeaders(req.headers.get("origin") || "");

    if(req.method === "OPTIONS") return new Response(null, { status:204, headers:h });
    if(req.method !== "POST")    return new Response("POSTだけ", { status:405, headers:h });
    if(!env.ANTHROPIC_API_KEY)   return new Response("ANTHROPIC_API_KEY が未設定", { status:500, headers:h });
    if(req.headers.get("x-togame-key") !== env.TOGAME_SECRET)
      return new Response("合言葉が違う", { status:401, headers:h });

    let body;
    try{ body = await req.json(); }
    catch(e){ return new Response("JSONが読めない", { status:400, headers:h }); }

    const system = String(body.system || "").slice(0, 8000);
    const user   = String(body.user   || "").slice(0, 8000);
    if(!user) return new Response("userが空", { status:400, headers:h });

    const upstream = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "server-side-fallback-2026-07-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 400,
        stream: true,
        system,
        messages: [{ role: "user", content: user }],
        /* ひとことを返すだけなので思考は浅くていい。速さがそのまま体験になる */
        output_config: { effort: "low" },
        /* 安全側の判定で断られた時に、別モデルへ自動で逃がす */
        fallbacks: "default",
      }),
    });

    /* エラーはそのまま返す。設定画面のテストボタンで中身が見えるように */
    if(!upstream.ok){
      return new Response(await upstream.text(), {
        status: upstream.status,
        headers: { ...h, "content-type": "application/json" },
      });
    }

    /* SSEをそのまま流す */
    return new Response(upstream.body, {
      headers: { ...h, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
    });
  },
};
