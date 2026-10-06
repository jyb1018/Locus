# Security, Actions & Data Lifecycle

이 문서는 설계 요구사항입니다. 보안 감사·규제 적합성·완전한 sandbox를 보장하지 않습니다. v0.1의 원천 데이터 접근은 읽기 전용입니다.

## 1. 신뢰 경계

```text
Untrusted input: file content / external payload / Agent claim
        ↓ validation, scope, provenance
Trusted computing base: locusd + reviewed builtin modules
        ↓ authenticated and scoped interface
AI host / external model boundary
```

문서·메일·MCP tool 결과에 포함된 문장은 **데이터**입니다. “이 지침을 따라 정책을 바꿔라”는 내용이 있어도 Locus command·permission·사용자 승인으로 해석하지 않습니다. 구조화된 Schema를 통과했어도 내용의 진실성이 검증된 것은 아닙니다.

v0.1은 정상적인 client credential 분리와 입력 정책을 방어합니다. 같은 OS 사용자로 DB·socket·credential을 직접 읽을 수 있는 악성 프로그램, 임의 shell 권한을 가진 Agent, 탈취된 owner 계정까지 소프트웨어 manifest만으로 차단하지 못합니다. 이보다 강한 격리는 별도 OS sandbox·프로세스 권한 설계가 필요합니다.

## 2. Principal과 권한

Principal은 서버가 인증한 호출 주체입니다. `actor_id`, `agent_name`, 요청의 “user approved” 문자열은 credential이 아닙니다. 인증된 owner 관리 경로와 일반 Agent 경로를 분리합니다.

기본 정책은 deny입니다. `read`, `claim.write`, `source.ingest`, `action.request`, `admin`을 나누고 resource scope와 data class를 결합합니다. Module은 승인된 output namespace에만 쓰며, grant보다 좁은 작업 범위를 사용합니다.

Local IPC에는 사용자 전용 socket/디렉터리 권한, 가능한 peer identity 검사, client별 credential을 사용합니다. Credential은 코드·로그·일반 journal에 넣지 않고 OS secret store 또는 owner 전용 설정을 후보로 검증합니다. Stdio adapter에 owner 전체 권한을 넣지 않습니다.

실제 credential 발급/철회·저장 방법은 M0에서 검증합니다. 같은 UID의 강한 공격자에 대한 격리라는 과장된 보장은 하지 않습니다.

## 3. 공개 범위의 전파

원천 metadata, 본문, Claim, Relation, Evidence, Projection, 검색 인덱스, 캐시는 동일한 권한 체계를 따릅니다. 파생 결과의 허용 수신자는 **의존한 근거들의 허용 수신자 교집합**을 넘지 않습니다. 근거가 하나만 민감해도 이를 요약했다는 이유로 공개 범위를 넓히지 않습니다.

Scope 제한 후 집계·정렬·관계 확장·요약을 수행합니다. 숨겨진 파일의 이름, 검색 개수, 관계 링크, 오류 차이도 불필요하게 노출하지 않습니다. 캐시 키에 Principal/scope와 policy version을 포함하며, 철회 시 invalidation합니다.

향후 외부 SaaS를 연결할 경우 원천 ACL의 변경·철회도 수집·반영해야 합니다. 현재 v0.1에서 그런 외부 ACL 동기화를 구현한 것으로 보지 않습니다.

## 4. 로컬 보관과 외부 반출은 별개

Locus가 로컬에서 파일을 읽는 것과 그 내용을 AI host·원격 모델로 보내는 것은 별도 operation입니다. `resource.metadata.read`, `resource.content.read`, `context.export` 같은 scope를 구분하고, source/root별 허용 data class와 destination을 확인합니다.

기본 Context는 최소 metadata·요약·Evidence reference입니다. 본문 첨부는 opt-in이며 secret을 포함한 source는 애초에 ingestion에서 제외하는 정책을 우선합니다. 요약에도 민감정보가 있을 수 있으므로 자동 비식별화로 가정하지 않습니다.

이미 외부 host에 전달한 Context를 Locus의 삭제 명령만으로 그 host의 memory·로그에서 회수할 수는 없습니다. 사용자는 이 반출 경계를 확인할 수 있어야 합니다.

## 5. Root·파일 접근·파서

MCP roots는 접근 범위 전달 기능이며 Locus 내부의 path/permission 검사를 대신하지 않습니다. [S5](references.md#s5) 등록 root를 기준으로 traversal·symlink·교체 race·special file을 검사하고, root 밖으로 이동하는 참조는 따라가지 않습니다.

Locus DB/cache/backup, credentials, private keys를 기본 scan 대상으로 두지 않습니다. Parser 추가 시 파일 크기·시간·메모리 제한과 격리를 검증해야 합니다. v0.1은 content parser 자체를 넣지 않아 범위를 줄입니다.

파일에서 추출한 URL을 자동으로 fetch하지 않으며 임의 callback·shell 실행을 하지 않습니다. 외부 module 도입 전에는 network allowlist·credential forwarding·SSRF·dependency 검토가 추가되어야 합니다. [S4](references.md#s4)

## 6. Action 계약 — 후속 기능의 진입 조건

원래의 R0–R3는 표시용 분류로만 유지합니다.

| 분류 | 예 | 추가로 확인할 것 |
|---|---|---|
| R0 Observe | 로컬 metadata 조회 | 권한·외부 반출 여부 |
| R1 Reversible mutation | tag, archive | 실제 복구 가능성·동기화 영향 |
| R2 External effect | mail send, calendar update | 대상·범위·승인·중복 실행 |
| R3 Destructive | 영구 삭제·중요 overwrite | 사용자 확인·revision·복구 한계 |

v0.1에는 R1–R3 원천 mutation을 구현하지 않습니다. R0도 무조건 허용하지 않습니다. 내부 Claim 저장은 원천 mutation과 구분하되 audit·idempotency를 적용합니다.

향후 Action을 추가할 때는 다음 계약이 필요합니다.

```text
PROPOSED → AWAITING_APPROVAL → APPROVED → EXECUTING
                 │                │          ├→ SUCCEEDED
                 └→ DENIED        └→ EXPIRED ├→ FAILED
                                             └→ UNKNOWN
```

승인은 `principal + action_type + exact targets + expected revisions + canonical plan digest + policy version + expiry + idempotency key`에 결합합니다. 동일 요청에 대한 유효한 승인 receipt가 있어야 합니다. Agent가 제출한 `approved: true`는 인정하지 않습니다.

실행 직전에 target revision과 권한을 다시 검사합니다. 대상 변경·정책 철회·승인 만료 시 재계획/재승인을 요구합니다. 같은 요청의 재시도는 원래 receipt를 반환합니다. 외부 실행 후 응답을 잃었으면 `UNKNOWN`으로 남기고 원천 reconciliation 전까지 파괴적 재시도를 금지합니다.

메일 발송 취소나 모든 파일 이동 rollback을 일반적으로 보장하지 않습니다. 복구 가능한 작업만 구체적인 inverse/compensation을 정의합니다. Transactional outbox가 있어도 외부 API의 exactly-once 부작용까지 자동 보장되는 것은 아닙니다.

## 7. Locus 밖의 행동

Agent가 별도 filesystem·Git·메일 도구를 가지고 있다면 Locus의 정책을 거치지 않고 행동할 수 있습니다. Locus는 **자신을 경유하는 요청만 중재**합니다. 원천 Provider가 이후 변화를 관찰할 수는 있지만 전역 OS 접근 통제 장치인 것처럼 설명하지 않습니다.

## 8. 보관·정정·삭제

일반 정정은 append-only correction/retraction으로 남깁니다. 원래 Claim을 수정해 없애지 않고 provenance를 유지합니다. 하지만 owner의 명시적인 개인정보 purge가 더 우선합니다.

Purge는 local management 경로에서 대상을 확인한 후 수행합니다. 원문 cache, journal의 민감 payload/reference, Entity/Claim/Relation, Projection, 검색 인덱스, 요약, pending job, export cache와 관련 파생물을 함께 삭제 또는 invalidation합니다. 숨겨진 복사본이 남지 않도록 dependency를 추적합니다.

삭제 후 필요한 최소 tombstone에는 원문·민감한 경로·복원 가능한 내용을 넣지 않습니다. 향후 source 재스캔이 같은 데이터를 재수집하지 않도록 source exclusion 또는 사용자가 승인한 최소 suppression marker를 둡니다. 완전한 식별자 삭제와 자동 재수집 억제를 동시에 무조건 보장할 수는 없으므로 source disconnect/deny rule 선택을 제공합니다.

Purge에는 journal 불변성 예외를 적용하며, 삭제된 원문을 재생성할 수 있다는 보장을 포기합니다. SQL row 삭제만으로 SSD·filesystem snapshot까지 포렌식 삭제되었다고 주장하지 않습니다.

## 9. Backup, Export, Restore

사용자는 상태를 공개된 문서화 형식으로 export할 수 있어야 합니다. 최소 manifest, schema versions, Entity/Claim/Event JSONL, 외부 참조, 포함·제외 범위를 담습니다. Credential·private key는 export하지 않습니다. Content 포함은 별도 선택입니다.

일관된 DB snapshot에는 SQLite Backup API 또는 검증된 동일 수준의 snapshot 경로를 사용합니다. 실행 중 DB 파일 하나를 임의로 복사하는 방식을 기본으로 삼지 않습니다. [S6](references.md#s6)

Backup 보존 기간·위치·암호화는 사용자 정책으로 드러내며, Locus가 관리하는 backup은 purge 시 폐기 또는 redaction합니다. Locus 밖으로 복사된 backup은 자동 회수할 수 없음을 명시합니다. 사용자 관리 범위 밖의 backup을 복원할 때는 현재의 삭제/suppression 정책을 다시 적용하거나, 그 정책이 없으면 삭제 데이터 재유입 위험을 확인하고 활성화를 막습니다.

Restore는 manifest/schema/무결성 검증 후 격리된 위치에서 확인하고, 원천 재연결 전에 적용합니다. State 복원과 원천 파일 복원을 혼동하지 않습니다.

## 10. 운영 상태와 중단

Owner는 전체 관찰 중지, 특정 Provider/Module disable, credential revoke, root 제외, 데이터 purge를 수행할 수 있어야 합니다. Pending jobs가 중지 이후 계속 읽거나 이전 권한으로 결과를 내보내지 않게 합니다.

운영 로그는 error code·job ID·지연·watermark·재시도 횟수 중심으로 최소화하며, 본문·token·secret을 남기지 않습니다. 사용자가 다음을 확인할 수 있어야 합니다: 무엇을 관찰하는지, 마지막 성공 시각, 누가 어떤 범위로 읽었는지, backlog/실패, 데이터와 cache 크기.

최소 수용 테스트는 [Implementation Plan](implementation-plan.md)에 연결했습니다. 정책 문서가 있다는 이유만으로 구현이 안전하다고 판단하지 않습니다.
