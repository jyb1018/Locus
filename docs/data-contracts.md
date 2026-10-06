# Data Contracts

이 문서는 v0.1.1의 **논리 계약**입니다. JSON 예시는 가상 데이터이며 실제 실행 API·JSON Schema 구현은 아닙니다. 모든 외부 입력은 구현 단계에서 schema와 도메인 제약을 검증해야 합니다.

## 1. 공통 규칙

ID는 workspace 내에서 안정적인 opaque ID를 사용합니다. 표시명·Agent 제품명·파일 경로를 권한 identity로 쓰지 않습니다. 시간은 offset을 포함한 RFC 3339로 받고 UTC로 저장하며, source가 발생 시점을 모르면 `occurred_at`은 null로 둡니다.

**인증 주체와 데이터 속의 행위자:** `principal_id`는 transport credential에서 결정합니다. `reported_actor`는 원천이 보고한 행위자일 뿐, 요청자 권한을 바꾸지 못합니다. `workspace_id`, 등록된 `source_id`, permission scope를 요청자의 문자열만으로 선택하게 하지 않습니다.

Namespace는 `locus.core.*`, `locus.resource.*`, `locus.gc.*` 등 등록된 소유자를 둡니다. 일반 Agent와 Module은 Core의 승인·정책·audit 이벤트를 생성할 수 없습니다. 등록되지 않은 event/predicate/schema version은 수용하지 않습니다.

## 2. 저장 모델

| 논리 테이블 | 내용 / 주요 제약 |
|---|---|
| `entities` | id, type, revision, 생성·관찰 정보 |
| `external_refs` | provider instance + namespace + external id의 유일성, 연결 이력 |
| `events` | 로컬 sequence, 검증된 출처, 최소 payload, provenance |
| `claims` | subject, predicate, value, kind, lifecycle, validity, evidence |
| `relations` | 관계 Claim의 인덱스. 독립적인 진실 저장소가 아님 |
| `projections` | resolver version, input watermark, 계산 결과, 공개 범위 |
| `sources` | root/scope, cursor, 최근 성공, coverage, health |
| `jobs` / `receipts` | module 실행·중복 억제·재시도·결과 |
| `policies` / `principals` | scope, credential reference, policy version, 철회 |

한 SQLite DB 안의 논리 구분입니다. 최종 DDL·migration 코드는 구현 시 작성합니다. Content cache와 secrets는 journal payload에 넣지 않습니다.

## 3. Event

Event는 **어떤 관찰 또는 입력이 수용되었는지**를 기록합니다. 그 payload가 외부 세계의 완전한 진실임을 의미하지 않습니다.

다음은 수용 후 저장된 레코드 예시입니다. Core가 `event_id`, `sequence`, `ingested_by`, `recorded_at`을 부여합니다.

```json
{
  "event_id": "evt_demo_001",
  "event_type": "locus.resource.observed",
  "schema_version": 1,
  "workspace_id": "ws_demo",
  "source_id": "src_files_demo",
  "source_event_key": "scan_001:res_demo_a:rev_4",
  "ingested_by": "principal_provider_files",
  "reported_actor": null,
  "sequence": 42,
  "occurred_at": null,
  "observed_at": "2026-10-06T02:00:00Z",
  "recorded_at": "2026-10-06T02:00:01Z",
  "subject_ids": ["res_demo_a"],
  "payload": {
    "resource_revision": "rev_4",
    "size_bytes": 2048,
    "modified_at": "2026-10-05T10:00:00Z"
  },
  "provenance": {
    "provider_id": "locus.filesystem",
    "provider_version": "0.1.0",
    "scan_id": "scan_001",
    "external_ref_id": "xref_demo_a"
  }
}
```

파일의 modified time은 마지막 관찰 시각과 다릅니다. `sequence`와 `recorded_at`이 나중이라고 해서 더 최신 원천 revision이라는 뜻은 아닙니다. Source revision/cursor가 없는 source는 수집 시각만으로 실제 변경 순서를 확정하지 않습니다.

### 수용 규칙

`(workspace_id, source_id, source_event_key)`를 unique로 둡니다. 같은 key와 같은 정규화 payload는 원래 receipt를 반환합니다. 같은 key에 다른 payload가 오면 `IDEMPOTENCY_CONFLICT`로 격리하며, 기존 기록을 덮어쓰지 않습니다.

Filesystem watcher의 중복 hint에는 source event ID가 없을 수 있습니다. Provider는 scan/read 작업 ID와 resource revision을 결합해 수용 key를 생성합니다. `파일명 + 수정 시각`만으로 모든 변경을 유일하게 식별한다고 가정하지 않습니다.

## 4. Claim

Claim의 최소 필드는 다음과 같습니다.

```text
claim_id, subject_id, predicate, value, schema_version
kind: OBSERVED | USER_ASSERTED | AGENT_INFERRED | DERIVED
created_by, evidence_refs[], recorded_at
valid_from?, valid_until?, expires_at?
lifecycle: ACTIVE | SUPERSEDED | RETRACTED
supersedes_claim_id?, confidence?, derivation?
```

`kind`는 입력 채널과 허용된 capability로 Core가 결정합니다. `USER_ASSERTED`는 사용자 관리/승인 경로, `OBSERVED`는 등록 Provider, `DERIVED`는 등록된 결정론적 resolver 경로만 생성합니다. 일반 MCP Claim은 `AGENT_INFERRED`입니다.

`confidence`가 있다면 `value`, `method`, `calibrated`를 함께 기록합니다. 서로 다른 모델의 미보정 점수를 비교해 이긴 Claim을 고르지 않습니다. Confidence 1.0도 fact·권한·사용자 승인으로 승격시키지 않습니다.

### Agent 입력 예시

```json
{
  "subject_id": "project_demo",
  "predicate": "locus.project.implementation_status",
  "value": "reported_complete",
  "evidence_refs": ["evt_demo_test_passed"],
  "expected_subject_revision": 7,
  "supersedes_claim_id": null,
  "idempotency_key": "demo_session_12_report_1"
}
```

입력에서 `created_by`, `kind`, `workspace_id`를 자칭할 수 없습니다. Evidence는 해당 Principal이 읽을 수 있고 사용 가능한 상태여야 합니다. 원문 reference와 그 내용을 실제로 검증한 것 역시 구분합니다.

근거가 없는 일반 note를 허용하는 predicate는 명시적으로 따로 정의해야 합니다. 그런 note는 “근거 부족”으로 저장할 수 있지만 authoritative projection의 근거로 자동 채택하지 않습니다. 도메인 상태 Claim은 기본적으로 최소 하나의 Evidence를 요구합니다.

저장 성공 응답은 `claim_id`, `recorded_sequence`, `subject_revision`, `projection_status`를 반환합니다. **accepted는 저장/형식 검증 성공이지 true 판정이 아닙니다.**

### 수명주기와 충돌

ACTIVE는 “현재 철회되지 않았다”는 뜻입니다. 최신·정확·충돌 없음의 보장이 아닙니다. `expires_at`이 지나면 fresh evidence로 사용하지 않지만 역사는 유지합니다.

등록된 predicate descriptor는 다음을 정합니다.

```text
value schema / cardinality
allowed claim kinds / authoritative sources
explicit supersession rules
freshness rules / dependency rules
resolver version
```

예를 들어 사용자 계획인 `project.intent_status`는 사용자 진술로 갱신하고, 개발 활동은 `development.last_activity_at`으로 계산합니다. 최근 커밋으로 사용자 계획을 덮어쓰지 않습니다. 같은 배타적 predicate에 유효한 주장들이 충돌하면 후보와 근거를 반환합니다.

자동 `last writer wins`는 사용하지 않습니다. 동일 authority가 **명시적으로 대체**하고 기대 revision이 맞는 경우만 supersession을 적용합니다. Resolver가 정책으로 값을 선택하더라도 충돌하는 유효 Claim이 있으면 대안과 선택 이유를 함께 유지합니다.

## 5. Relation

관계는 `subject → predicate → object` 형태의 Claim으로 취급합니다. 직접 검증된 연결과 추정 연결을 구분하고, 관계 인덱스에는 Claim ID를 연결합니다.

숨겨진 Entity를 가리키는 관계는 조회자에게 드러내지 않습니다. Relation의 Evidence가 철회·삭제되면 관련 Projection을 invalidation합니다. 외부 ID의 검증된 일치는 연결 근거가 될 수 있지만, 동일 Hash나 비슷한 이름만으로 identity를 합치지는 않습니다.

## 6. Projection과 Context 응답

Resolver는 현재 필드별로 `RESOLVED / CONFLICTED / UNKNOWN`을 반환합니다. 최신성은 별도로 `FRESH / STALE / UNKNOWN`, 관찰 범위는 `COMPLETE / PARTIAL / UNKNOWN`으로 표시합니다. 값이 존재한다고 최신성이나 관찰 완전성이 자동으로 보장되지는 않습니다.

응답에는 최소 다음 metadata를 포함합니다.

```json
{
  "snapshot_sequence": 84,
  "materialized_through": 80,
  "projection_version": "resource-context/1",
  "policy_version": 3,
  "generated_at": "2026-10-06T02:05:00Z",
  "freshness": "STALE",
  "coverage": "PARTIAL",
  "reasons": ["source_offline", "module_backlog"],
  "items": [],
  "truncated": false,
  "next_cursor": null
}
```

이는 응답 envelope 형태 예시이며 빈 `items`가 실제 상태라는 뜻은 아닙니다. Item별 value, resolution, evidence_refs, source observation time을 별도로 제공합니다.

`materialized_through`는 필요한 module stream에서 빈틈 없이 처리한 watermark입니다. 실패한 이벤트를 건너뛰고 더 뒤의 sequence를 완료 watermark로 표시하지 않습니다. `freshness`는 journal 처리 여부와 source의 최근 성공 여부를 함께 고려합니다.

Core canonical write 직후 읽기는 해당 command의 저장 결과를 볼 수 있어야 합니다. 비동기 Module 결과까지 즉시 보장하지 않습니다. 조회자가 `min_sequence`를 요구했는데 준비되지 않았다면 `PROJECTION_PENDING`과 재시도 정보를 반환하고 오래 기다리지 않습니다.

### 제한된 응답

조회는 scope와 관련성 필터를 적용한 후 budget 내에서 결과를 반환합니다. 처음에는 metadata·요약·근거 reference를 주고, 본문은 별도 권한 아래 필요할 때 읽습니다.

초기 응답 정책 후보는 기본 32 KiB, hard cap 128 KiB의 UTF-8 직렬화 크기입니다. 실제 SDK/MCP envelope를 포함한 한도는 spike에서 고정합니다. token 수는 tokenizer가 없으면 추정치로만 표시합니다. Truncation은 숨기지 않으며, Evidence 본문을 자동 덧붙이지 않습니다.

Cursor는 Principal·workspace·filter·policy version·상한 sequence·만료에 결합합니다. 다른 Principal이 재사용하거나 권한이 바뀌면 거부합니다. 캐시도 같은 공개 범위에 묶으며 revoked credential로 과거 cached 결과를 받게 하지 않습니다.

## 7. 동시성, 멱등성, Crash

Canonical 변경은 command receipt, journal append, 현재 테이블 변경을 같은 트랜잭션에 넣습니다. Source checkpoint도 해당 수용 단위와 원자적으로 갱신합니다. 파일 읽기·network·LLM·긴 계산 중에는 write transaction을 열어 두지 않습니다.

명시적 수정/대체에는 `expected_subject_revision`을 요구합니다. 불일치하면 `VERSION_CONFLICT`를 반환하고 자동 overwrite하지 않습니다. 새 독립 Claim은 expected revision 없이 받을 수 있지만, 이 경우 기존 Claim의 supersession은 허용하지 않습니다.

일반 command의 dedup 범위는 `(principal_id, workspace_id, idempotency_key)`입니다. 동일 key·동일 의미 입력은 저장된 원래 결과를 반환합니다. Key 재사용 시 semantic payload가 달라지면 거부합니다.

Module 처리는 at-least-once 재시도를 전제로 합니다. `(module_id, module_version, projection_version, input_event_id)`별 receipt를 두고 결과 Claim·receipt·cursor 갱신을 함께 commit합니다. Batch 입력이면 안정적인 input-set key를 사용합니다. “모든 외부 효과까지 exactly once”를 약속하지 않습니다.

오류는 유한 횟수 재시도 후 격리하고 Projection을 degraded로 표시합니다. 초기 후보는 최대 5회이며 backoff는 설정값입니다. 독성 이벤트 하나로 전체 daemon을 죽이거나 무한 재시도하지 않습니다. 실패 gap이 있는 watermark는 전진시키지 않되 독립 module은 계속 동작할 수 있습니다.

## 8. Replay, Schema, 삭제

Projection replay는 보존된 데이터와 고정된 resolver version의 결정론적 계산입니다. 외부 시스템 변경, LLM 호출, 원문 재수집을 replay에 섞지 않습니다. 재분석이 필요하면 새 command와 새 Claim으로 구분합니다.

Schema 버전과 Projection 버전은 분리합니다. Migration 전 consistent backup을 만들고 변환 테스트를 수행합니다. 지원하지 않는 버전은 임의로 해석하지 않습니다. Upgrade 실패 시 마지막 정상 Projection을 stale로 표시하고 오류를 드러냅니다.

데이터 purge 후에는 완전 replay를 보장할 수 없습니다. 영향을 받은 Projection·Relation·Evidence·캐시를 삭제 또는 invalidation하고, 필요하면 개인정보를 포함하지 않는 최소 tombstone만 유지합니다. Purge 전 backup에서 다시 살아나는 문제까지 [Security](security-and-lifecycle.md) 정책으로 처리합니다.

## 9. 오류 계약

| 코드 | 의미 / 재시도 |
|---|---|
| `NOT_FOUND_OR_FORBIDDEN` | 존재 여부를 권한 밖에 노출하지 않음 |
| `INVALID_ARGUMENT` / `UNSUPPORTED_SCHEMA` | 형식·도메인 제약·버전 확인 필요 |
| `VERSION_CONFLICT` | 최신 revision을 다시 읽고 사용자/Agent가 조정 |
| `IDEMPOTENCY_CONFLICT` | 같은 key에 다른 요청. 자동 재시도 금지 |
| `PROJECTION_PENDING` | 지정 watermark에 미도달. 제한된 재시도 |
| `SOURCE_UNAVAILABLE` | 외부 상태 확인 불가. 없음/삭제로 해석 금지 |
| `MODULE_UNAVAILABLE` | 미설치·중지·실패 상태. 마지막 결과 freshness 확인 |
| `BUDGET_EXCEEDED` | scope/limit을 줄이거나 pagination 사용 |
| `CURSOR_INVALIDATED` | 정책·보존 범위 변경. 권한 확인 후 새 snapshot |
| `UNSUPPORTED_ACTION` | v0.1에서 원천 mutation을 지원하지 않음 |

MCP protocol error와 tool execution error를 구분합니다. Locus 도메인 오류는 구조화된 `code`, `retryable`, 안전한 설명을 담고, 실패를 성공처럼 반환하지 않습니다. 구체적인 매핑은 [S3](references.md#s3)의 도구 오류 모델을 기준으로 구현합니다.
