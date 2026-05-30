# hermes-plugin-hindsight-sanitize

External Hermes plugin that strips multimodal blobs (image/audio data URLs,
inline base64) from the content passed to Hindsight retain.

## Why

Image / audio user-messages arrive at the Hindsight provider as OpenAI-style
content lists:

```json
[{"type": "text", "text": "подпись"},
 {"type": "image_url",
  "image_url": {"url": "data:image/png;base64,iVBOR..."}}]
```

If that's stringified verbatim into a retain payload, a multi-MB base64 blob
lands in the Hindsight bank document. Consequences:

- Postgres row size balloons → vacuum churn
- Embedding model chokes on garbage tokens → recall returns junk neighbours
- `recall_max_tokens` budget burns on a single attachment

Stripping the blob and keeping a `[image: ~280KB inline]` placeholder
preserves "user sent text + one image" semantics without the pixels.

## How

`register()` wraps `HindsightMemoryProvider._build_turn_messages` so each
non-text content part is sanitized into a one-line placeholder before the
upstream method builds the retain dict.

The static helper is also attached to the class as
`HindsightMemoryProvider._sanitize_for_retain` for callers that need it
explicitly.

No upstream files are edited.

## Use

```yaml
# config.yaml
plugins:
  enabled:
    - hindsight-sanitize
```

## Mounting

```yaml
# docker-compose.hermes-core.yml
volumes:
  - ./sources/hermes-external-plugins/hindsight-sanitize:/opt/data/plugins/hindsight-sanitize:ro
```
