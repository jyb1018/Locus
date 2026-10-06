# Locus Core Architecture — 검토 및 변경 기록

- 검토일: 2026-10-06
- 입력: 이 대화의 **Locus v0.1 — Core Architecture** 23개 절 및 앞선 Personal GC Context Snapshot
- 결과: **v0.1.1 설계 기준안**. 제품 방향은 유지하고, 모순·실행 가능성·안전 경계·검증 기준을 보강했습니다.
- 이 문서는 구현 코드 리뷰나 독립 보안 감사가 아닙니다. 새로 정한 수치와 구현 순서는 이번 검토의 제안이며 측정 결과가 아닙니다.

## 총평

**여러 Agent의 기억을 하나로 합치는 대신, 사용자 소유의 근거 있는 상태를 공유한다**는 방향은 유지할 가치가 있습니다. Provider / Module / Core 분리, 작은 MCP 표면, Fact와 Inference 분리도 유지합니다.

다만 이전 초안의 “개념 설계는 닫혔고 타입만 만들면 된다”는 결론은 이릅니다. 수집 누락, 쓰기 충돌, 권한 전파, 삭제, 호스트 연결 방식이 정해지지 않은 상태에서는 구현마다 다른 시스템이 됩니다. 특히 `Locus maintains reality`는 과한 약속이므로 **Locus maintains evidence-backed state within its observed scope**로 좁혔습니다.

## 주요 피드백과 반영

P0는 보안·데이터 무결성의 구현 전 필수 경계, P1은 첫 수직 기능 흐름의 정확성·실용성을 위한 요구, P2는 후속 검증 대상으로 사용합니다. 실제 장애가 발견되었다는 의미는 아닙니다.

| 우선순위 | 기존 초안의 빈틈 | 개선한 설계 | 상세 |
|---|---|---|---|
| P0 | Agent가 `record_event`로 관찰된 사실이나 사용자 확인을 자칭할 수 있음 | 일반 Agent는 `record_claim`만 사용합니다. Principal과 입력 종류를 서버가 결정하고, Provider ingestion·사용자 승인 경로를 분리합니다. | [Data Contracts](data-contracts.md) |
| P0 | 서로 다른 Agent의 판단을 어떤 기준으로 현재 상태에 반영하는지 없음 | Predicate별 권위·기수성·명시적 대체 규칙을 두고, 해결 불가 시 `CONFLICTED`를 반환합니다. 사용자 의도와 실제 활동은 별도 필드입니다. | [Data Contracts](data-contracts.md) |
| P0 | View를 다르게 보여주는 것과 접근 통제를 동일시 | 조회·검색·집계·관계 확장·Evidence·캐시 모두에서 권한을 적용합니다. 파생 결과는 근거의 가장 제한적인 공개 범위를 물려받습니다. | [Security](security-and-lifecycle.md) |
| P0 | “영구 immutable history”와 사용자 데이터 삭제가 충돌 | 일반 수정은 append-only로 남기되, 명시적 purge는 예외입니다. 파생 상태·인덱스·캐시·백업 정책까지 삭제 경계를 정의합니다. | [Security](security-and-lifecycle.md) |
| P0 | 동일 OS 사용자 권한으로 실행되는 플러그인까지 manifest로 격리할 수 있는 것처럼 보임 | v0.1은 신뢰한 내장 모듈만 허용합니다. Manifest는 선언이지 sandbox가 아니며, 임의 플러그인 실행은 제외합니다. | [Modules](modules-and-mcp.md) |
| P1 | MCP 연결을 대화 수집·hook·자동 호출·알림 전달의 보장으로 취급 | Host capability를 별도 검증합니다. MCP는 연결 계약이며 host의 대화 접근·실행 정책을 대체하지 않습니다. | [Modules](modules-and-mcp.md), [S1](references.md#s1) |
| P1 | Local-first인데 상위 Agent가 원격 서비스일 수 있음 | 첫 대상은 로컬 MCP host입니다. Hosted-only 클라이언트에는 별도 bridge가 필요할 수 있으며, 연결 지원을 미리 선언하지 않습니다. | [Architecture](architecture.md), [S2](references.md#s2) |
| P1 | stdio 연결마다 별도 Runtime이 생길 가능성 | `locusd` 하나가 DB·수집기를 소유하고 host별 stdio adapter는 IPC로 연결합니다. | [Architecture](architecture.md) |
| P1 | 모든 이벤트가 완전한 사실이고 원천 시스템보다 권위 있다고 가정 | 외부 시스템의 snapshot/관찰과 Locus가 소유하는 Claim·승인 기록을 구분합니다. 관찰 범위와 최신성을 응답에 포함합니다. | [Architecture](architecture.md) |
| P1 | 중복 이벤트·순서 역전·crash 후 재처리 계약 없음 | Source별 dedup key, 로컬 commit sequence, 트랜잭션, module receipt·cursor와 유한 재시도를 명시합니다. | [Data Contracts](data-contracts.md) |
| P1 | 파일 watcher가 완전한 변경 이력이라고 가정 | 최초 scan + 변경 hint + reconciliation으로 구성합니다. 불완전 scan이나 끊어진 root는 삭제로 해석하지 않습니다. | [Modules](modules-and-mcp.md), [S7](references.md#s7) |
| P1 | Event sourcing을 모든 데이터에 강제 | 단일 DB에서 현재 테이블과 의미 있는 변경 journal을 함께 유지합니다. 전체 세계를 완전 replay할 수 있다는 약속은 하지 않습니다. | [Architecture](architecture.md) |
| P1 | Projection 재생 시 LLM 재실행·외부 행동 가능성이 열려 있음 | Replay는 보존된 입력·Claim·버전 기반의 순수 계산만 허용합니다. LLM 결과는 별도 Claim으로 기록하며 행동을 재실행하지 않습니다. | [Data Contracts](data-contracts.md) |
| P1 | Confidence 0.85 같은 수치를 권위 또는 안전 확률로 해석할 여지 | 미보정 confidence는 설명 보조 정보입니다. Fact 승격·권한 부여·삭제 승인 기준으로 쓰지 않습니다. | [Data Contracts](data-contracts.md) |
| P1 | 모듈을 제거하면 과거 의미·Projection이 어떻게 되는지 불명확 | Disable 시 write 중지·drain·stale 표시, uninstall은 detach와 purge를 분리합니다. 스키마와 데이터 출처는 보존합니다. | [Modules](modules-and-mcp.md) |
| P1 | 읽기를 R0로 묶고 무조건 안전하다고 취급 | 로컬 조회와 외부 모델로의 데이터 반출을 분리합니다. 비가역성 외에 공개 범위·대상·양도 판단합니다. | [Security](security-and-lifecycle.md) |
| P1 | 승인을 받으면 어떤 시점에도 행동 가능 | 향후 Action은 정확한 대상 revision·계획 digest·권한·만료에 승인을 결합합니다. 실행 전 재확인하고 결과 불명은 `UNKNOWN` 처리합니다. | [Security](security-and-lifecycle.md) |
| P1 | GC만 시연해도 공통 State OS 검증으로 보기 쉬움 | 두 Principal의 상태 공유·접근 차단·재시작 복구·상충 Claim을 수용 기준에 추가합니다. | [Plan](implementation-plan.md) |
| P2 | Runtime이 모든 Agent의 직접 외부 도구 호출까지 통제하는 것처럼 보임 | Locus 경유 요청만 통제합니다. 우회 호출은 관찰 후 반영할 수 있을 뿐, 전역 강제 정책이 아닙니다. | [Security](security-and-lifecycle.md) |

## 유지한 것

Locus / Personal State OS라는 이름, 사용자 소유 State, 교체 가능한 Agent, Provider와 의미 모듈의 구분, Event / Claim / Relation / Projection, 근거 추적, 최소한의 권한 중재, 로컬 우선 전략은 유지합니다.

Personal GC, Open Loop, Handoff, Meeting, Automation Finder는 계속 확장 후보입니다. 다만 **후보가 있다는 것과 v0.1에서 모두 구현한다는 것은 다릅니다.**

## 구현량을 줄인 것

첫 GC는 읽기 전용 중복 탐지로 제한했습니다. 의미 판단용 LLM, 자동 archive/delete, temp 파일의 단순 연령 기반 삭제 판정은 보류합니다. UI는 최소한의 로컬 관리·검토 경로만 필요하며, 범용 플러그인 설치기·외부 MCP aggregator·Event Bus·Vector DB는 첫 버전 요구가 아닙니다.

`0.85 confidence`, `7일`, tool 응답 용량 같은 값은 기존 또는 신규 **초기 정책 후보**일 뿐 검증된 최적값이 아닙니다. 비용·지연 목표도 구현 후 측정해야 합니다.

## 아직 닫지 않은 결정

구현 언어/SDK, 실제 host별 연결 방법, 파일 식별·보안 API의 macOS 구현, 로컬 credential 저장 방식, 파서 격리 방식은 spike와 테스트로 결정합니다. 특정 Dot·Muse 제품의 비공개 기능을 가정하여 설계를 닫지 않습니다.

전체 방향은 [Core Architecture](architecture.md), 구현 착수 순서는 [Implementation Plan](implementation-plan.md)을 따릅니다.
