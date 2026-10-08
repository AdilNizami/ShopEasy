# Backward compatibility policy

Contracts are promises to independent clients and consumers. A change is backward compatible only when existing conforming callers can continue using the new producer/consumer without changing their behavior. Review both request and response behavior and include event consumers that may be deployed later than publishers.

## REST API

Usually compatible within `/v1`:

- Add an optional request field with a documented default/absence behavior.
- Add an optional response field while clients are required to ignore unknown response fields.
- Add a new endpoint or optional query parameter that does not alter existing behavior.
- Broaden accepted input without changing the meaning of previously accepted input.

Potentially or definitely breaking:

- Remove or rename an endpoint, field, or response value; change a field type, format, nullability, or meaning.
- Make an optional request field required, tighten validation so formerly valid requests fail, or change a default.
- Remove a response field or make it absent/null where it was guaranteed.
- Change status-code semantics, ordering/pagination behavior, money precision, or an established error code's meaning.
- Add a response enum value when clients may reject unknown values; treat as breaking unless consumers are explicitly tolerant.
- Change authentication or idempotency semantics in a way that requires caller changes.

For breaking REST changes, publish a new URL major version (`/v2`) and OpenAPI document. Run versions in parallel for a communicated migration period. Do not silently repurpose `/v1`.

## Events and JSON Schema

The event envelope is defined in `contracts/events/event-envelope.schema.json`; each named event has an immutable v1 schema. Consumers must ignore unknown optional properties and validate required fields and supported versions. Producers must not change the meaning of existing fields.

Usually compatible:

- Add an optional field to `data` with clear semantics.
- Add a new event type without changing existing event types.
- Broaden accepted optional data without changing current field semantics.

Potentially or definitely breaking:

- Remove/rename a required property; change its type, format, constraints, or meaning.
- Add a required property to an existing event version.
- Tighten validation so a previously valid event is rejected.
- Change event type, version interpretation, producer ownership, or the meaning/timing of the fact.
- Make an optional property required, or change its nullability.

For a breaking event payload, publish a new major schema version, such as `PaymentConfirmed.v2.schema.json`, and set the envelope `version` to `2`. Use a staged rollout: deploy consumers that understand both versions, then publishers of v2, observe migration, and retire v1 only after all consumers have moved. If old and new consumers must coexist, publish a new event type or explicitly route both schema versions; never reinterpret a v1 message. Keep event IDs stable on redelivery and preserve duplicate-safe consumer behavior during migration.

## Review checklist

Before merging a contract change, identify affected callers/consumers, classify it using this policy, validate the OpenAPI/JSON Schemas, check representative old payloads against the new contract, and document rollout/retirement steps for any major version. Schema validity alone does not prove behavioral compatibility.
