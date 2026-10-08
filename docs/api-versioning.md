# API versioning

## Initial version

The initial REST contract is OpenAPI 3.1 in [`contracts/openapi/shop-easy-v1.yaml`](../contracts/openapi/shop-easy-v1.yaml). Its server base path is `/v1`; operations append resources such as `/products` and `/orders`. Thus the product collection is `/v1/products`. Keep the version in the URL so a caller and gateway can identify the contract in use without guessing from headers or media types.

The OpenAPI `info.version` identifies the document revision (`1.0.0`); it does not replace the `/v1` URL version. Compatible changes can update the document revision while preserving `/v1`. An incompatible public contract change introduces `/v2` and a separate OpenAPI document.

## Rules

- Version the public API as a whole at the URL boundary. Do not version individual fields or endpoints independently without a clear need.
- Keep response evolution additive and keep established meanings stable within `/v1`.
- Clients should tolerate unknown response fields. Servers should validate documented request fields and return the documented error envelope.
- A new major URL version may run alongside the previous one during migration. Publish migration notes, provide a defined support window, and remove `/v1` only after consumers have migrated and the retirement is communicated.
- Do not use a version bump to avoid compatibility review. First determine whether an additive change is sufficient.
- Error codes and enum values are contract values; adding an enum value can break clients that exhaustively match the list, so document and review it as potentially breaking.
- Correlation and idempotency headers do not change the resource version. Mutations must reuse their idempotency key on retry.

The current endpoints cover product listing/details, cart, order creation/checkout, order reads/status, and payment request/status. They define wire shapes only; they do not select an implementation, storage model, or service decomposition.
