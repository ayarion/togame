/* トガメのエージェント用プロキシ。
   APIキーは静的HTMLに置けない（GitHub Pagesは世界中から読める）ので、
   Cloudflare Workers を1枚だけ挟んでキーをこちら側に隠す。

   デプロイ:
     npx wrangler secret put ANTHROPIC_API_KEY   # Anthropicのコンソールで発行したキー
     npx wrangler secret put TOGAME_SECRET       # 自分で決める合言葉。トガメの設定にも同じものを入れる
     npx wrangler deploy

   合言葉は、このWorkerを他人に勝手に使われて課金が伸びるのを防ぐためだけのもの。 */

const MODEL = "claude-haiku-4-5";

/* Opus 5 / Sonnet 5 系だけが受け付けるオプションがある。
   Haiku 4.5 に effort や fallbacks を送ると 400 で落ちるので、モデルで切り替える。
   MODEL を claude-opus-5 に戻せば、そのまま元の設定に戻る */
const IS_FRONTIER = /^claude-(opus|sonnet|fable)-(5|4-[678])/.test(MODEL);

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

function anthropicHeaders(env){
  const h = {
    "content-type": "application/json",
    "x-api-key": env.ANTHROPIC_API_KEY.trim(),
    "anthropic-version": "2023-06-01",
  };
  /* 安全側の判定で断られた時に別モデルへ逃がす仕組み。上位モデルのみ */
  if(IS_FRONTIER) h["anthropic-beta"] = "server-side-fallback-2026-07-01";
  return h;
}

function buildPayload(system, user){
  const p = {
    model: MODEL,
    max_tokens: 1000,
    stream: true,
    system,
    messages: [{ role: "user", content: user }],
  };
  if(IS_FRONTIER){
    /* ひとことを返すだけなので思考は浅くていい。速さがそのまま体験になる */
    p.output_config = { effort: "low" };
    p.fallbacks = "default";
  }
  return p;
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
      headers: anthropicHeaders(env),
      body: JSON.stringify(buildPayload(system, user)),
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
