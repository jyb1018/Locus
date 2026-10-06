# Providers, Modules & MCP

아래 manifest·tool·lifecycle은 **Locus 자체 계약의 제안**입니다. MCP 표준에 내장된 plugin/OS 기능이 아닙니다. 실제 SDK와 구현 코드는 아직 없습니다.

## 1. 세 경계

**Provider:** 원천의 관찰·동기화·커서를 책임집니다. **Module:** 도메인 타입·Claim·Projection·전문 도구를 제공합니다. **Adapter:** Locus 계약을 in-process 호출, local IPC 또는 외부 MCP에 연결합니다.

MCP server가 도구를 노출한다고 해서 Locus가 그 데이터의 identity, revision, 수명주기, 출처를 자동으로 아는 것은 아닙니다. 외부 MCP를 모듈로 쓰려면 이 의미를 매핑하는 adapter가 필요합니다. 일반 RPC polling과 정규화된 이벤트 ingestion은 별도 책임입니다.

## 2. Provider 계약

Provider는 자신의 instance ID, 허용 root/scope, 외부 ID namespace, source cursor, 최근 성공 시각, 오류와 coverage를 제공합니다. 가능한 한 관찰된 사실을 내보내며, 추론은 Claim으로 구분합니다.

수집의 기본 형태는 다음과 같습니다.

```text
initial scan / initial sync
          ↓
change hints or polling
          ↓
re-read authoritative source
          ↓
normalized observations + checkpoints
          ↓
periodic or recovery reconciliation
```

모든 원천 변경의 exactly-once 알림을 전제하지 않습니다. Apple FSEvents도 coalescing·dropped event와 재스캔 상황을 문서화합니다. [S7](references.md#s7)

Provider 재시작 시 마지막 성공 checkpoint와 실제 source 상태를 대조합니다. Source가 접근 불가하거나 scan 일부가 실패했다면 `PARTIAL` 또는 `UNKNOWN`으로 보고합니다. 완전한 성공 scan에서 사라진 대상만 source-specific missing 상태로 전이시킬 수 있습니다. “목록에 없음”은 즉시 파일 삭제 확정이 아닙니다.

## 3. Filesystem Provider v0.1

사용자가 고른 디렉터리의 일반 파일을 읽기 전용으로 처리합니다. 기본 수집은 metadata와 필요 시 size + content Hash입니다. 본문 파서, OCR, 임베딩, 네트워크 전송은 첫 범위가 아닙니다.

Root allowlist와 제외 규칙을 수집 전에 적용합니다. Credentials, `.env`, key material, `.git` 내부, Locus DB/cache 등은 기본 제외 대상으로 명시합니다. 제외 목록은 사용자 설정이 필요하며, 이 목록만으로 모든 secret을 탐지할 수 있다고 보장하지 않습니다. 제외 파일의 민감한 이름·내용도 로그에 남기지 않습니다.

Symlink를 따라가지 않고 허용 범위 밖으로 나가지 않습니다. 단순 문자열 prefix 검사를 넘어 traversal, 파일 교체 race, special file을 방어할 OS별 접근 방식을 검증합니다. MCP roots만으로 이 경계가 강제되지는 않습니다. [S5](references.md#s5)

Scan은 파일 수·총 읽기량·개별 파일 크기·시간 예산을 갖습니다. 초과하면 `PARTIAL`로 종료하고 재개 정보를 제공합니다. 읽기 전후의 file identity/revision을 대조하여 바뀐 파일의 결과는 재검증 대상으로 둡니다. 부하를 제한한 hint 처리와 재스캔이 필요하며, 파일 변경 하나마다 LLM을 호출하지 않습니다.

동일 inode를 가리키는 hardlink alias와 별도 파일 사본을 구분합니다. 안정적인 identity가 확인되지 않으면 근거를 보존하고 판단을 보류합니다. Filesystem 정책을 제품 기능과 분리해 테스트합니다.

## 4. Personal GC Module v0.1

첫 기능은 **중복 그룹과 검토 후보를 근거와 함께 제공**하는 것입니다. 원천 파일을 수정하지 않습니다.

같은 size·content Hash를 가진 일반 파일을 그룹화합니다. Hash가 같다는 것과 그 경로를 지워도 된다는 것은 다르므로, 사용자 지정 대표본·보존 조건이 없으면 삭제 대상으로 임의 확정하지 않습니다. `DELETE_CANDIDATE`를 표시하는 경우에도 유지할 사본과 각 revision을 명시하며, 실행 권한은 없습니다.

`KEEP / ARCHIVE / REVIEW / DELETE_CANDIDATE` enum은 기존 개념을 유지합니다. 다만 첫 구현은 duplicate evidence와 `REVIEW` 중심이며, “중복이 아니다”만으로 `KEEP`이라는 의미 판단을 만들어내지 않습니다. 명시적인 사용자 pin은 보존 정책으로 반영할 수 있습니다.

구버전은 삭제하지 않습니다. Temp·partial download가 7일 지났다는 사실만으로 disposable 판정을 확정하지 않습니다. Zero-byte의 의도적 marker 예외도 필요하므로 첫 버전에서는 이런 케이스를 검토 대상으로 남깁니다. 의미 기반 archive, version-family, LLM escalation은 후속입니다.

## 5. Module manifest 예시

이 YAML은 v0.1.1의 개념적 manifest입니다. 최종 parser/schema와 설치 CLI는 아직 구현하지 않았습니다.

```yaml
manifest_version: 1
module:
  id: locus.personal-gc
  version: 0.1.0
  core_api: "0.1"
  execution: builtin
  trust: owner-approved-first-party
requires:
  capabilities:
    - locus.resource.metadata
    - locus.resource.content_hash
consumes:
  - type: locus.resource.observed
    schema_version: 1
produces:
  - type: locus.gc.analysis_recorded
    schema_version: 1
provides:
  predicates:
    - locus.gc.duplicate_group
  projections:
    - id: locus.gc.candidates
      version: 1
permissions:
  requested:
    - resource.metadata.read
    - resource.content_hash.read
    - claim.write:locus.gc.*
  source_mutations: []
processing:
  replay: recorded-inputs-only
  idempotency: input-event-and-module-version
  max_attempts: 5
tools:
  - locus_gc_candidates
lifecycle:
  on_disable: drain-and-mark-stale
  on_uninstall: detach-preserve-data
```

Manifest에 `permission`을 썼다는 이유로 권한이 생기지 않습니다. 설치/활성화 시 owner가 부여한 실제 grant와 교집합을 사용합니다. v0.1의 `builtin`은 신뢰 경계 내부이며, untrusted package sandbox가 아닙니다.

## 6. Lifecycle와 탈착

```text
REGISTERED → ENABLED → DISABLED → DETACHED
                 └→ DEGRADED
```

Register는 schema·namespace·호환성·요구 capability를 검증합니다. Enable은 승인한 grant로만 처리합니다. Disable은 새 작업을 멈추고 진행 중 작업을 drain 또는 취소하며, 마지막 Projection에 `module_disabled` stale 사유를 남깁니다.

Detach는 실행 연결을 제거하는 것입니다. 과거 관찰, Claim, schema descriptor, provenance를 자동 삭제하지 않습니다. Unknown module payload도 데이터로 읽거나 export할 수 있어야 하며, 해석 불가 상태를 숨기지 않습니다. 오래된 코드를 자동 재실행해서 이해하려 해서는 안 됩니다.

Purge는 owner의 별도 명령입니다. 다른 모듈이 의존하는 data와 Projection을 확인하고 invalidation합니다. Upgrade는 module/schema/projection 버전을 기록하고 migration·replay를 검사합니다. 모든 버전의 자동 rollback을 약속하지 않습니다.

한 모듈 실패가 다른 module의 receipt·journal을 손상시키지 않도록 오류를 격리합니다. 같은 process의 native code crash까지 완전 격리되는 것은 아니므로, process 분리는 실제 crash·권한·자원 격리 요구가 생길 때 적용합니다.

## 7. Agent-facing MCP 표면

기본 도구 후보는 아래 여섯 개입니다. 실제 `tools/list`에는 허용된 도구만 노출하고 호출 시에도 다시 권한을 검사합니다. 도구를 목록에서 감추는 것만으로 권한 통제가 완성되지는 않습니다.

| 도구 | 목적 |
|---|---|
| `locus_search` | 허용 범위의 Entity·Claim 검색 |
| `locus_get_entity` | Entity 및 허용된 근거 세부 조회 |
| `locus_get_context` | scope·budget·freshness를 가진 Context 조회 |
| `locus_list_changes` | Principal-bound cursor 이후 변경 조회 |
| `locus_record_claim` | Agent 추론/보고의 명시적 제출 |
| `locus_get_status` | 허용 범위의 Provider·Module health와 coverage |

Filesystem/GC는 필요할 때 `locus_files_scan`, `locus_files_scan_status`, `locus_gc_candidates`를 추가합니다. Scan을 요청하는 권한과 Provider observation을 직접 기록하는 권한은 다릅니다. 시간이 긴 scan은 job ID와 상태 조회로 처리하며 하나의 tool call을 무제한 유지하지 않습니다.

일반 Agent에게 `record_event`, 임의 SQL, shell command, 정책 수정, 사용자 승인 위조 기능은 제공하지 않습니다. 원천 mutation 도구와 `request_action`은 v0.1에 노출하지 않습니다.

Input/output schema를 정하고, domain error는 명시적인 tool error로 반환합니다. 필요하면 `structuredContent`와 text fallback을 함께 사용합니다. MCP annotations는 UI 힌트이지 authorization 근거가 아닙니다. [S3](references.md#s3)

## 8. Host와 hook의 현실성

| 항목 | Locus 기본 제공 | 별도 확인 |
|---|---|---|
| Tool을 통한 Context 조회/Claim 제출 | 설계 대상 | 해당 host의 MCP 지원·설정 |
| AI 대화 전문 자동 수집 | 제공하지 않음 | 공식 export/event/hook과 사용자 동의 |
| 매 턴 자동 Context 주입 | 보장하지 않음 | host extension/hook 기능 |
| 비활성 AI를 깨워서 추론 실행 | 제공하지 않음 | 명시적인 scheduler·지원 API |
| 로컬 watcher 지속 실행 | `locusd` 역할 | 장치 실행·권한·daemon 상태 |
| Hosted-only AI에서 local State 사용 | v0.1 범위 밖 | bridge, transport, 인증·반출 정책 |

MCP server는 host 전체 대화를 자동으로 받지 않습니다. Host의 lifecycle·context 관리와 capability 협상을 존중해야 합니다. [S1](references.md#s1) 따라서 Dot·Muse·Codex라는 이름만으로 자동 연결이 검증된 것으로 기록하지 않습니다.

첫 통합은 **로컬 stdio를 지원하는 실제 host 두 개**에서 검증합니다. 두 test client는 Core 검사에 쓸 수 있지만, 그 결과만으로 실제 제품 두 개의 통합 성공을 선언하지 않습니다.

## 9. 저비용 실행 원칙

수집·중복 제거·필터링·검색은 로컬 코드로 처리합니다. 기본 경로의 LLM 호출은 0회입니다. Agent는 필요한 Context만 받고 상세 Evidence를 추가 조회합니다.

모든 도구 schema를 항상 길게 늘어놓거나 전체 event history를 매번 전송하지 않습니다. Cached projection은 데이터 revision·resolver·policy·scope를 포함해 식별하고 freshness를 확인합니다. 재분석이 필요한 후속 의미 Module만 명시적인 budget과 consent 아래 LLM을 사용합니다.

외부 MCP module을 여러 단계 proxy할 때 권한·오류·지연을 감추지 않습니다. 네트워크 경계를 늘리는 것보다 **독립 교체의 실제 가치**를 먼저 확인합니다.
