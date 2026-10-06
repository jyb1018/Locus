# Locus v0.1.1 — Core Architecture

> **Personal State OS · One state. Any compatible agent.**

상태: 구현을 위한 **설계 기준안**. 2026-10-06 대화의 v0.1 초안을 검토·보강한 문서이며, 구현·성능·안전성 검증 완료를 뜻하지 않습니다. 변경 이유는 [Architecture Review](architecture-review.md)에 기록했습니다.

## 1. 책임 경계

Locus는 Agent와 독립적으로 사용자 소유의 상태를 유지합니다.

```text
Observe → Normalize → Persist → Relate → Project → Expose
                                      └→ Govern mediated actions
```

Core는 구조 검증, 출처·권한, 저장, 결정론적 Projection을 담당합니다. 의미 추론은 Agent 또는 선택한 의미 모듈이 담당합니다. “Core가 추론하지 않는다”는 말은 임의의 의미 해석을 숨겨 넣지 않는다는 뜻이지, 규칙·검색·집계가 없다는 뜻이 아닙니다.

**권위 경계:** 파일·메일·캘린더의 실제 상태는 각 원천 시스템이 소유합니다. Locus는 내부 Entity ID, Claim 이력, 사용자 승인, 정책, 작업 receipt를 소유합니다. 외부 상태의 Projection은 관찰 시각과 범위를 가진 materialized view이지 외부 시스템의 대체 원장이 아닙니다.

범용 Agent orchestration, 자체 모델 라우터, 기업 조직 모델, 완전한 디지털 생활 감시는 책임에 포함하지 않습니다.

## 2. 논리 구조와 실행 구조

```text
AI hosts / local tools
        │ MCP or management CLI
        ▼
Adapters ── authenticated local IPC ── locusd
                                      │
                                      ├─ Core: identity, claims, journal,
                                      │        projections, access, receipts
                                      ├─ Providers: facts from allowed sources
                                      ├─ Modules: domain-specific projections
                                      └─ SQLite + optional local content cache
```

v0.1은 **단일 사용자·단일 장치·단일 daemon**입니다. `locusd`가 DB writer와 Provider 수명주기를 소유합니다. Host별 stdio adapter는 독립 DB나 watcher를 갖지 않습니다. Stdio에서 client가 server subprocess를 실행하는 특성 때문에 이 경계를 분리합니다. [S2](references.md#s2)

로컬 IPC는 사용자 전용 Unix domain socket을 우선 후보로 둡니다. 동시 시작은 workspace lock으로 직렬화하고, daemon이 없으면 명시적인 관리 경로로 시작합니다. 여러 adapter의 무제한 자동 daemon 생성은 금지합니다. Windows 지원은 v0.1 필수 요구가 아닙니다.

## 3. 최소 Primitive

| Primitive | 의미 | Core의 책임 |
|---|---|---|
| Entity | 지속적 내부 ID를 가진 대상 | ID, type namespace, 외부 참조, revision |
| Event | 어떤 입력·관찰·상태 전이가 수용되었는지의 기록 | 출처 검증, 중복 방지, 로컬 순서, 보존 정책 |
| Claim | 특정 대상·predicate에 대한 관찰 또는 주장 | 종류, 근거, 유효 기간, 대체·철회 이력 |
| Relation | Entity 사이의 관계 | 연결 대상과 관계 Claim의 출처·공개 범위 |
| Projection | 기록에서 계산된 현재 관점 | 계산 버전, watermark, 상태·충돌·최신성 |
| Principal / Actor | 요청 권한 주체 / 사건의 행위자 | 인증 주체와 보고된 행위자를 분리 |
| Policy | 허용 범위와 승인 규칙 | 기본 거부, 범위 검사, 버전·철회 |

`Project`, `Resource`, `Commitment`, `Decision`, `Session`은 등록된 도메인 타입입니다. Core에 모든 도메인 동작을 하드코딩하지 않습니다. “최소 Primitive”가 곧 7개의 독립 서비스나 7개의 독립 DB를 의미하지는 않습니다.

## 4. 입력에서 Agent View까지

```text
Provider observation / Agent claim / Human command
                       ↓
Authenticate → authorize → validate → deduplicate
                       ↓
Resolve verified identities / preserve ambiguous references
                       ↓
Transaction: journal + canonical records + core projection
                       ↓
Durable module jobs → derived claims / module projections
                       ↓
Permission-filtered, budgeted context for each principal
```

Raw payload는 무조건 보존하지 않습니다. 허용한 최소 metadata와 원천 reference를 기본으로 저장하며, 본문 cache와 외부 LLM 전송은 별도 정책을 따릅니다. 구조 정규화와 의미 추론을 구분합니다.

## 5. Event와 State: 제한된 journal + 현재 테이블

“모든 것을 Event로만 저장”하지 않습니다. v0.1은 현재 Entity/Claim/Relation 테이블과 의미 있는 변경 journal을 **같은 DB 트랜잭션**으로 갱신합니다. Projection은 재생성 가능하도록 설계하되, 원천 내용·지워진 데이터·누락된 외부 변경까지 복원할 수 있다고 주장하지 않습니다.

일반적인 수정은 correction/retraction 기록으로 남깁니다. 명시적 개인정보 삭제는 append-only 원칙의 예외이며, [삭제 계약](security-and-lifecycle.md)을 우선합니다.

예를 들어 “프로젝트를 중단하기로 했다”와 “어제 커밋이 생겼다”는 모순이 아닐 수 있습니다. `project.intent_status = paused`와 `development.last_activity_at = ...`를 동시에 유지합니다. 둘을 성급하게 `project.status = active`로 합치지 않습니다.

## 6. Event Envelope

공통 필드와 입력/저장 레코드의 구분은 [Data Contracts](data-contracts.md)에 정의합니다. 핵심은 다음과 같습니다.

`event_id`, `event_type`, `schema_version`, `workspace_id`, `source_id`, `source_event_key`, `ingested_by`, `occurred_at`, `observed_at`, `recorded_at`, `sequence`, `subject_ids`, `payload`, `provenance`.

`ingested_by`, `recorded_at`, `sequence`는 Core가 부여합니다. Provider가 보낸 실제 발생 시각은 없거나 부정확할 수 있습니다. `sequence`는 로컬 commit 순서이며 전 세계 사건의 실제 시간 순서가 아닙니다. Event에 `confidence: 1.0`을 붙여 진실성을 보증하지 않습니다.

## 7. Fact, Assertion, Inference

Claim의 기존 네 종류는 유지합니다.

- `OBSERVED`: 허용된 Provider가 직접 관찰한 값입니다. 관찰 범위 밖의 완전성은 보장하지 않습니다.
- `USER_ASSERTED`: 인증된 사용자 관리·확인 경로에서 받은 진술입니다.
- `AGENT_INFERRED`: Agent의 해석 또는 보고입니다. “사용자가 말했다”는 Agent 보고도 자동으로 사용자 진술이 되지 않습니다.
- `DERIVED`: 특정 버전의 결정론적 규칙으로 계산한 결과입니다.

저장 성공은 Claim의 진실성 승인이 아닙니다. Confidence는 선택적인 보조 정보이며, 권위·권한·삭제 안전성을 대신하지 않습니다. 재생 시 LLM을 다시 부르지 않고 기존에 기록한 결과를 이용합니다.

## 8. Identity Resolution

내부 Entity ID와 `(provider_instance, external_namespace, external_id)`를 분리합니다. 같은 이메일 문자열, 파일명 또는 본문 Hash만으로 다른 Entity를 자동 병합하지 않습니다.

파일 내용의 동일성은 파일 identity의 동일성이 아닙니다. 경로 변경과 inode 재사용을 고려해야 하며, 확실한 rename 근거가 없는 경우 새 Entity와 가능한 관계를 남기는 편을 우선합니다. Provider별 식별 전략과 한계는 수용 테스트로 고정합니다.

사용자 확인을 통한 병합은 외부 참조의 이력과 되돌릴 연결 정보를 보존합니다. v0.1에는 모호한 cross-service 자동 병합을 넣지 않습니다.

## 9. 쓰기와 충돌

Agent는 DB·Projection·정책을 직접 수정하지 않습니다. 일반 MCP 입력은 `record_claim`으로 제한하고, Provider ingestion과 사용자 관리 command는 별도 인터페이스입니다.

기존 Claim을 대체하는 command는 기대 revision을 검사합니다. 동시에 들어온 서로 다른 Claim은 단순 덮어쓰지 않고 모두 남길 수 있습니다. Predicate별 resolver가 허용된 출처, 유효성, 명시적 supersession을 적용하고 결정할 수 없으면 `CONFLICTED`를 반환합니다.

구체적인 멱등성·낙관적 동시성·재처리 규칙은 [Data Contracts](data-contracts.md)를 따릅니다.

## 10. Shared State, Scoped View

View는 Agent 이름으로 고정하지 않습니다. 인증된 Principal의 scope와 요청 목적에 맞춰 생성합니다. 같은 Agent라도 프로젝트 A와 B에 다른 credential을 사용할 수 있습니다.

권한으로 데이터를 먼저 제한하고, 그 안에서 Context를 구성합니다. 숨겨진 Entity의 존재·개수·제목·관련 링크가 집계나 Evidence를 통해 새어 나오지 않게 합니다. 파생 정보는 근거의 공개 제약을 유지합니다.

## 11. Permission Model

읽기, Claim 제출, 원천 ingestion, Action 요청, 관리 권한을 분리합니다. Scope는 최소한 workspace·entity/resource 범위·operation·data class를 포함합니다. Principal은 transport에서 인증하며, 요청 JSON의 `actor_id`나 `source`만 믿지 않습니다.

v0.1은 하나의 owner 아래 여러 제한된 client credential을 둡니다. 조직용 RBAC/ABAC 엔진까지 만들지는 않습니다. 로컬 악성 프로그램이나 강한 shell 권한을 가진 Agent를 manifest만으로 격리할 수 있다는 주장은 하지 않습니다.

## 12. Action Risk와 승인

초안의 R0–R3는 설명용 분류로 유지하되 자동 승인 규칙으로 사용하지 않습니다. **읽기도 외부 모델에 전달되면 정보 공개**가 됩니다. Permission, 데이터 반출 범위, 가역성, 외부 영향, 대상 revision을 함께 판단합니다.

v0.1은 원천 파일과 외부 서비스에 쓰지 않습니다. 향후 Action 계약은 [Security & Lifecycle](security-and-lifecycle.md)에 별도로 둡니다. Journal replay가 실제 행동을 재실행해서는 안 됩니다.

## 13. Provider와 Module

Provider는 허용된 원천을 관찰·동기화하고 cursor, 성공/실패, 관찰 범위를 보고합니다. Module은 입력을 해석하거나 도메인 Projection을 만듭니다. 한 패키지가 두 역할을 제공할 수 있지만 계약은 구분합니다.

Provider가 중지되면 데이터는 사라지는 것이 아니라 freshness가 낮아집니다. 원천에서 조회되지 않았다는 이유만으로 존재하지 않는다고 확정하지 않습니다.

## 14. Module Contract

Manifest는 소비·생성 이벤트, 도메인 타입·predicate, Projection, 요구 권한, 호환 Core 버전, schema/projection 버전, 실행·재시도 정책, 제거 시 보존 정책을 선언합니다.

Module이 자기 output namespace를 소유하더라도 Core의 인증·audit·permission namespace에는 쓸 수 없습니다. Manifest와 구체적인 lifecycle은 [Modules & MCP](modules-and-mcp.md)를 따릅니다.

## 15. Native와 MCP 경계

Logical Module Contract와 transport를 분리합니다. 초기에는 검토한 내장 모듈을 같은 배포 단위에서 사용하고, 필요할 때만 독립 process 또는 MCP adapter를 추가합니다.

**MCP 지원만으로 Locus Module이 되는 것은 아닙니다.** Identity, provenance, 이벤트 ingest, permission, freshness, retry 계약을 잇는 adapter가 있어야 합니다. MCP를 ABI·Event Bus·package manager로 간주하지 않습니다.

## 16. Agent-facing MCP

작은 조회/Claim 도구 집합을 기본으로 둡니다. 목록은 [Modules & MCP](modules-and-mcp.md)에 정의합니다. 표준 `tools/list`, `tools/call` 위에 Locus 도메인 도구를 제공합니다. 응답은 구조화하고 입력·출력 schema를 검증합니다. [S3](references.md#s3)

MCP 연결만으로 host 대화 전문, 매 턴 hook, 자동 context 주입, 비활성 AI 호출이 생기지는 않습니다. 특정 host와의 연결·권한·자동 호출 여부는 별도 통합 테스트 대상입니다. [S1](references.md#s1)

## 17. Attention과 전달

`SILENT / ON_QUERY / SURFACE / INTERRUPT`는 상태를 다루는 정책 후보로 유지합니다. v0.1은 `SILENT`와 `ON_QUERY`만 구현합니다.

나중에 전달 기능을 추가할 때 중복 억제, cooldown, 만료, 사용자 중단, delivery receipt를 정의해야 합니다. `SURFACE`는 host가 다음 문맥에 실제 반영했다는 보장이 아니며, `INTERRUPT`도 별도의 검증된 알림 채널 없이는 제공하지 않습니다.

## 18. Storage와 실행 보장

v0.1의 저장소 제안은 **로컬 SQLite 하나**입니다. 논리적으로 current records, event journal, module jobs/receipts, projection checkpoints, policy registry를 구분합니다. 본문 cache는 별도로 둘 수 있습니다. WAL에서도 동시 writer는 하나이므로 Core의 단일 write 경로와 짧은 트랜잭션을 유지합니다. [S6](references.md#s6)

무거운 scan·hash·파싱·LLM 호출은 DB 트랜잭션 밖에서 수행합니다. 결과 수용 시 입력 revision을 다시 확인합니다. 초기에 Redis, Kafka, 별도 graph/vector DB를 요구하지 않습니다.

## 19. Local-first와 호스트 현실성

v0.1 기본은 사용자 로컬 장치입니다. MCP는 host별 stdio adapter를 우선 대상으로 하며, Cloud-only host가 이 구성을 직접 사용할 수 있다고 가정하지 않습니다.

원격 접근이 필요하면 인증된 gateway, 전송 암호화, 동의·반출 정책, 해당 host의 지원 여부를 별도 설계합니다. 임시 공개 tunnel을 기본 해결책으로 삼지 않습니다. Local-first는 “LLM까지 모두 로컬”이라는 뜻이 아니므로 host로 내보내는 필드를 별도로 통제합니다.

## 20. 기존 기능의 위치

| 기존 개념 | Locus의 위치 | v0.1 |
|---|---|---|
| Personal GC | Resource Lifecycle Module | 읽기 전용 중복 후보 흐름 |
| Open Loop Tracker | Commitment Projection Module | 보류 |
| Future-Me Handoff | Session / Checkpoint Module | 후속. Core 공유 Claim 복구와는 구분 |
| Meeting Agent | Meeting Provider + 의미 Module | 보류 |
| Automation Finder | Event Pattern Analysis Module | 보류 |

## 21. 설계 원칙

사용자 소유 State, 관찰과 해석 분리, 근거·최신성 노출, 작은 Core, 모델 중심 추론, 명시적 module contract, 최소 권한, 사용자의 최종 통제권을 유지합니다.

“Observe once”는 중복 수집을 줄이자는 목표이지 재검증을 금지하는 원칙이 아닙니다. “State is persistent”도 사용자가 삭제할 수 없다는 뜻이 아닙니다.

## 22. v0.1 Scope

첫 수직 기능 흐름은 **한 Provider, 한 Module, 두 Client**입니다. 허용된 폴더의 파일 metadata/Hash를 수집하고, 근거가 있는 duplicate group을 저장·조회합니다. 일반 Agent의 Claim 제출, 다른 Agent의 조회, 재시작 복구, 권한 차이와 충돌을 함께 검증합니다.

전체 의미 GC, 자동 삭제·이동, 외부 SaaS, 일반 플러그인 실행, LLM worker는 제외합니다. Scope와 성공 기준은 [Implementation Plan](implementation-plan.md)에 고정합니다.

## 23. 열린 결정과 설계 종료 조건

구현 언어·MCP SDK, 실제 host 2개, credential 전달 방식, OS별 안전한 파일 접근 API, 대규모 디렉터리 성능은 아직 검증하지 않았습니다.

M0 통합 spike와 실패 조건 테스트를 통과해야 구현 선택을 확정합니다. 새로운 모듈을 늘리는 대신 **같은 데이터에 대해 두 Agent가 일관된 근거·권한·최신성을 보는지**로 첫 설계를 평가합니다.
