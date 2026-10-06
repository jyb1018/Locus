# Implementation Plan & Acceptance Criteria

**현재 상태:** 아키텍처 문서만 있습니다. 아래 M0–M4는 아직 실행하지 않은 구현 계획입니다. 수치가 있는 항목도 성능 측정 결과가 아니라 초기 목표/실험 조건입니다.

## 1. 첫 제품 가설

> 한 Agent가 확보한 근거 있는 상태를, 다른 Agent가 원천 전체를 다시 읽지 않고도 자신의 권한 안에서 이어서 사용할 수 있는가?

이를 검증하기 위한 첫 범위는 **단일 사용자 / 단일 장치 / 한 Filesystem Provider / 한 읽기 전용 GC Module / 두 Client**입니다. 단순 중복 파일 검색만 성공하면 Locus 가설을 검증한 것이 아닙니다.

## 2. 유지할 경계

`locusd` 하나와 SQLite 하나를 중심으로 시작합니다. Core 모듈을 별도 네트워크 서비스로 나누지 않고 내장 모듈을 사용합니다. LLM, Event Bus, graph/vector DB는 필수 dependency가 아닙니다.

원천 파일 수정·archive·delete, 외부 SaaS 쓰기, 자동화 실행, 임의 외부 plugin, remote gateway, enterprise 지원은 제외합니다. 파일 파서와 semantic GC도 첫 milestone에서 제외합니다.

## 3. M0 — 연결과 실행 경계부터 검증

로컬 stdio MCP를 실제 지원하는 host 두 개를 선정합니다. 각 host의 버전, transport, credential 입력 경로, Tool 호출·결과 처리, 수동 또는 자동 호출 방식, 대화/hook 접근 여부를 기록합니다. 특정 제품의 비공개 기능은 가정하지 않습니다.

두 stdio adapter가 같은 local daemon에 연결하고, 동일 owner workspace 내 서로 다른 Principal로 인증되는지 확인합니다. 동시 daemon 시작, 종료 후 재연결, credential revoke를 시험합니다. 단일 사용자 OS 환경에서 실제로 보장하는 격리 수준을 문서화합니다.

**완료 기준:** 실제 두 host에서 같은 synthetic Entity를 읽되 서로 다른 권한이 적용됩니다. 먼저 test client 두 개만 연결했다면 “Core transport 검증”으로 표시하고 제품 통합 성공으로 격상하지 않습니다.

이 단계에서 구현 언어와 MCP SDK를 선택하고 버전을 고정합니다. Local-only 호스트로 사용자 목표를 달성할 수 없다고 확인되면 remote bridge 범위를 명시적으로 재검토합니다. 연결 불가능한 제품 지원을 README에 먼저 광고하지 않습니다.

## 4. M1 — Core 저장·Claim·Projection

Entity/external refs, source registry, Event journal, Claim, 단순 Relation 인덱스, resolver, Principal/policy, command receipt를 구현합니다. 논리 계약은 [Data Contracts](data-contracts.md)를 따릅니다.

서로 다른 client가 Claim을 제출하고 조회하는 흐름부터 만듭니다. Duplicate command, stale revision, 권한 위조, 상충 Claim, daemon restart를 synthetic fixture로 검증합니다. Inference와 사용자 확인 경로를 분리합니다.

**완료 기준:** journal와 현재 테이블이 crash 시 서로 엇갈리지 않고, 새 client가 provenance와 freshness를 가진 동일한 허용 상태를 복구합니다. 사용자가 중단한 프로젝트에 commit이 생겨도 의도 상태를 자동으로 active로 바꾸지 않습니다.

## 5. M2 — Filesystem + 읽기 전용 GC

사용자 지정 root의 bounded initial scan, metadata·Hash observation, scan checkpoint, source coverage를 구현합니다. 그 뒤 change hint와 reconciliation을 추가합니다. 처음부터 모든 파일 형식의 본문 파싱을 지원하지 않습니다.

GC는 동일 size·Hash 그룹과 관련 evidence를 반환합니다. 경로 역할이나 대표본이 불명확하면 `REVIEW`입니다. 사용자 pin과 명시적인 대표본 정책이 없다면 안전한 삭제를 주장하지 않습니다. 원천 파일 변경은 전혀 하지 않습니다.

**완료 기준:** 두 host가 동일한 duplicate evidence를 보고, 같은 파일의 revision이 바뀌면 이전 결과가 stale 또는 invalidated로 표시됩니다. Symlink·특수 파일·excluded secret·불완전 scan을 안전하게 처리합니다.

## 6. M3 — 실패·보존·탈착

Module jobs/receipts, 유한 재시도, gap-aware watermark, disable/drain, export/restore, purge 및 파생 데이터 invalidation을 구현합니다. Clock offset과 source 지연을 가정하여 `occurred_at`의 정렬만으로 상태를 덮어쓰지 않는지 확인합니다.

**완료 기준:** 중단·재시작·module 비활성화가 영구적인 중복 Claim이나 거짓 fresh 상태를 만들지 않습니다. 동일 내용이 export/cache/파생물에 남아 purge를 우회하지 않도록 검증합니다. 사용자 관리 범위 밖의 backup/외부 host 회수는 지원 불가 범위를 명시합니다.

## 7. M4 — 사용자 흐름 평가

한 client가 파일 상태를 조회하고 검토 note Claim을 남깁니다. 다른 client가 허용된 scope에서 이를 이어받습니다. 원천 파일 변경, 권한 철회, daemon 재시작을 끼워 넣어 같은 결과와 올바른 차단이 유지되는지 확인합니다.

**완료 기준:** 상태 복구의 유용성이 단일 Agent의 임시 memory와 구별되며, source 전체 재수집 없이 현재 필요한 범위와 근거를 전달합니다. 실제 반복 사용 결과를 바탕으로 다음 Module을 정합니다.

## 8. 필수 수용 테스트

아래는 **작성해야 할 테스트 목록**이며 이 문서 커밋에서 통과한 테스트가 아닙니다.

| ID | 상황 | 통과 조건 |
|---|---|---|
| A01 | 같은 source event를 100회 수용 | canonical event/효과는 1회, 같은 receipt |
| A02 | 같은 idempotency key에 다른 payload | 명시적 conflict, overwrite 없음 |
| A03 | 늦게 도착한 과거 source revision | 최신 관찰을 과거 값으로 덮어쓰지 않음 |
| A04 | 두 client가 같은 revision을 대체 | 하나만 성공, 다른 쪽 version conflict |
| A05 | 독립적인 상충 Claim | 두 근거 보존, policy에 따라 충돌 또는 선택 이유 표시 |
| A06 | Agent가 user/provider를 자칭 | 권위 승격 거부, 인증 Principal 유지 |
| A07 | 숨겨진 Entity 검색·집계·관계 | 이름·개수·Evidence로 권한 밖 정보를 누출하지 않음 |
| A08 | Credential/scope 철회 후 cache/cursor 재사용 | 이전 권한으로 조회 불가 |
| A09 | 트랜잭션 중 crash 후 재시작 | journal/current records/receipt 일관성 |
| A10 | Module 계산 후 commit 전 crash | 재처리 가능, 결과 중복 없음 |
| A11 | poison event 및 다른 module 실행 | 실패 격리, watermark gap 표시, 독립 처리 유지 |
| A12 | watch event 누락·root offline·부분 scan | reconciliation, false deletion 없음 |
| A13 | symlink/traversal/파일 교체/special file | root 밖 읽기 없음, 안전 실패 또는 REVIEW |
| A14 | 같은 Hash지만 다른 역할 또는 hardlink | Hash만으로 삭제 안전성/동일 Entity를 확정하지 않음 |
| A15 | `.gitkeep`·빈 marker·오래된 temp | 연령/크기만으로 삭제 확정하지 않음 |
| A16 | Module disable/uninstall | 새 처리 중지, 기존 결과 stale, 자동 데이터 삭제 없음 |
| A17 | Projection replay | 외부 행동·LLM 호출 0회, 보존 입력에 대해 재현 가능 |
| A18 | Purge 후 검색/export/관계/캐시/backup | 관리 범위 내 복사·파생물을 제거/무효화, 복원 위험 공개 |
| A19 | 문서에 policy 변경 지시 삽입 | 데이터로만 취급, 권한·승인 변경 없음 |
| A20 | 두 실제 host + daemon 재시작 | 공유 state 지속, host별 scope 유지 |
| A21 | Context 크기 cap 초과 | bounded response, truncation/cursor 명시 |
| A22 | gc 후보 생성 후 원본 파일 변경 | revision mismatch로 기존 결과 stale/invalidation |
| A23 | 원천 mutation 또는 approval 위조 요청 | v0.1 미지원/권한 거부, 파일·외부 서비스 변경 없음 |

## 9. 측정 항목

로컬 metadata 기준 1천/1만 resource fixture와 크기 분포가 알려진 파일 집합으로 scan·Hash 비용을 따로 측정합니다. Metadata query와 대용량 파일 Hash 시간을 하나의 숫자로 합치지 않습니다.

측정값은 hardware, OS, DB/SDK version, 데이터 크기, cold/warm cache 여부와 함께 남깁니다. Read latency의 초기 목표 후보는 warm metadata/context 조회 p95 250 ms 이내지만, **아직 측정하거나 달성한 수치가 아닙니다.** 큰 파일 분석은 async job으로 분리합니다.

필수 계측은 p50/p95 조회 지연, source freshness, queue lag, 실패/재시도, DB/cache 크기, bytes read/exported, context 크기, LLM 호출 수입니다. v0.1 기본 경로의 LLM 호출 수 목표는 0회입니다. 범위 밖 데이터 노출·source mutation은 0건이어야 합니다.

## 10. 다음 모듈 선택

M0–M4 이후에 Git Provider + Handoff, 또는 Meeting/Open Loop 중 실제로 자주 쓰는 흐름 하나를 고릅니다. 모듈 목록을 채우기 위해 구현하지 않습니다. Automation Finder는 의미 있는 이벤트가 쌓인 뒤 검토합니다.

새 infrastructure는 다음 질문을 통과해야 합니다: 현재 수용 테스트를 만족시키는 데 필요한가, 단일 배포 구조로 해결할 수 없는가, 독립 배포·격리·교체의 실제 이점이 있는가?

## 11. 아직 필요한 의사결정 기록

구현 언어/SDK와 host matrix, source identity/revision 전략, credential 저장·owner 관리 경로, schema/retention 기본값, macOS의 안전한 파일 접근 API는 각 spike 결과와 함께 짧은 결정 기록으로 추가합니다.

지금 하지 않을 결정은 enterprise abstraction, marketplace, cross-device consensus, 범용 LLM router입니다. 아키텍처를 더 넓히는 대신 위 검증 항목을 닫는 것을 다음 단계로 삼습니다.
