CSP nonces now stay live across the SSE / `EventStream` drain. Previously
`CSPNonceMiddleware` reset its nonce `ContextVar` in a `finally` the instant the
handler returned — before `handle_sse` produced any event — so a framework inline
script emitted inside a yielded `Fragment` (`format_oob_script`,
`alpine_json_config`, `safe_data_helper`, or `<script nonce="{{ csp_nonce() }}">`)
streamed with a dead/empty nonce, the same lifecycle bug fixed for `Suspense` in
#181. The live nonce is now captured at negotiation time, carried on `SSEResponse`,
and re-established inside the SSE producer task for the connection's whole lifetime
(mirroring the `StreamingResponse` drain in `send_streaming_response`), so every
event on a long-lived stream renders with the stable per-request nonce.
([#194](https://github.com/lbliii/chirp/issues/194))
