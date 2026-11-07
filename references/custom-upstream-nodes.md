# Registering a Custom OpenAI-Compatible Upstream Node in 9Router

Use when adding a local or third-party OpenAI-compatible gateway (e.g. zcode-gateway, any `http://host/v1/` endpoint) as a provider in 9Router. Two steps are REQUIRED; the node alone is not enough.

## Procedure

1. **Create the node** — registers the upstream identity:

   ```bash
   curl -s -X POST http://localhost:20128/api/provider-nodes \
     -H "Content-Type: application/json" \
     -d '{"name":"my-gateway","prefix":"zc","apiType":"chat","baseUrl":"http://127.0.0.1:20131/v1/"}'
   ```

   Returns a node id like `openai-compatible-chat-<uuid>`. Record it.

2. **Create the connection** — attaches credentials to that node. Without this, model requests fail with `No active credentials for provider: <nodeId>`.

   ```bash
   curl -s -X POST http://localhost:20128/api/providers \
     -H "Content-Type: application/json" \
     -d '{
       "provider": "openai-compatible-chat-<uuid>",
       "authType": "apikey",
       "name": "zc",
       "apiKey": "dummy",
       "defaultModel": "glm-5.3-flash",
       "providerSpecificData": {
         "prefix": "zc",
         "apiType": "chat",
         "baseUrl": "http://127.0.0.1:20131/v1/",
         "nodeName": "my-gateway",
         "connectionProxyEnabled": false,
         "connectionProxyUrl": "",
         "connectionNoProxy": ""
       }
     }'
   ```

   `apiKey` can be a dummy literal when the gateway is local and auth-open; 9Router only needs a non-empty credential row.

3. **Verify end-to-end** through 9Router itself (not the gateway directly):

   ```bash
   curl -s -X POST http://localhost:20128/api/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"zc/glm-5.3-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'
   ```

   Model id format is `<prefix>/<model>`. A streamed `reasoning_content` / usage response confirms the whole chain works.

## Pitfalls

- **Node ≠ connection.** `POST /api/provider-nodes` alone leaves the provider with no active credentials; requests return `No active credentials for provider`. The connection (step 2) is the missing half.
- **Dummy apiKey is fine for auth-open local gateways**, but a provider that truly checks the key needs the real one.
- **The combo gateway stays a separate long-running process.** 9Router only proxies to it; it does not start it. If the gateway dies or the machine reboots, the node goes 502 until the gateway is restarted.
