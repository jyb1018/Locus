# Locus

### Personal State OS

> **One state. Any compatible agent.**

Locus는 여러 AI Agent가 함께 사용할 수 있는 **사용자 소유의 지속적인 상태 계층**입니다. Agent가 바뀌어도 프로젝트·리소스·결정·작업 맥락을 이어갈 수 있도록, 관찰과 해석을 구분해 저장하고 필요한 범위만 제공합니다.

여기서 OS는 하드웨어 운영체제나 Agent 실행 프레임워크가 아니라 **Agent와 개인의 디지털 환경 사이의 상태·권한·수명주기 중재 계층**이라는 뜻입니다.

**상태: 설계 기준안 v0.1.1 / 2026-10-06.** 이 저장소에는 검토 및 개선한 아키텍처 문서가 있습니다. 실행 가능한 daemon, SDK, MCP 서버는 아직 구현하지 않았으며, 특정 AI 제품과의 연결도 아직 검증하지 않았습니다.

```text
AI host A ── stdio adapter ──┐
                            ├── local IPC ── locusd ── SQLite
AI host B ── stdio adapter ──┘                  │
                                              ├── Filesystem Provider
                                              └── Personal GC Module
```

각 host가 별도 MCP 프로세스를 실행하더라도 adapter는 같은 `locusd`를 이용합니다. 독립 DB와 수집기를 Agent마다 만드는 구조는 피합니다. 이것은 첫 구현을 위한 설계안이며, 작동 확인된 제품 구성은 아닙니다.

## 핵심 원칙

- **State belongs to the user.** Agent 교체와 상태 보존을 분리하며, 사용자는 내보내기·삭제·접근 철회를 통제합니다.
- **Evidence before authority.** 관찰·사용자 진술·Agent 추론을 구분하고, 출처와 최신성을 함께 제공합니다.
- **Reasoning stays with the model.** Core는 범용 추론이나 Agent 조직도를 구현하지 않습니다.
- **Small core, explicit contracts.** 기능은 모듈로 확장하되, 모든 내부 경계를 MCP나 마이크로서비스로 나누지 않습니다.

Locus는 외부 세계의 절대적 진실이 아닙니다. **관찰 가능한 범위에서 확보한 근거와 현재의 해석을 관리합니다.** 파일·메일 등 원천 데이터의 권위는 원천 시스템에 남습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [아키텍처 검토](docs/architecture-review.md) | 기존 초안의 문제, 수정 이유, 유지한 방향 |
| [Core Architecture](docs/architecture.md) | 책임 경계, 데이터 흐름, 저장·실행 모델 |
| [Data Contracts](docs/data-contracts.md) | Event·Claim·Projection, 동시성, 오류·응답 계약 |
| [Modules & MCP](docs/modules-and-mcp.md) | Provider·Module 계약, 탈착, 도구와 host 연결 |
| [Security & Lifecycle](docs/security-and-lifecycle.md) | 권한, 신뢰 경계, 행동 승인, 삭제·백업 |
| [Implementation Plan](docs/implementation-plan.md) | 첫 구현 범위, 수용 기준, 아직 열린 결정 |
| [References](docs/references.md) | 외부 기술 근거와 적용 범위 |

문서는 **대화에서 합의한 제품 방향 / 이번 검토에서 제안한 설계 / 구현 검증이 필요한 항목**을 구분합니다. 기준 문서는 Core Architecture이며 상세 계약은 해당 문서를 따릅니다. 문서화가 구현 완료나 안전성 검증을 의미하지 않습니다.

## v0.1의 첫 검증 범위

단일 사용자·단일 로컬 장치에서, 지정 디렉터리를 읽기 전용으로 관찰하고 중복 후보를 근거와 함께 제공합니다. 서로 다른 두 클라이언트가 같은 상태와 Claim을 읽고, daemon 재시작 후에도 상태가 이어지는지 검증합니다.

첫 단계에는 외부 서비스 쓰기, 파일 이동·삭제, LLM 기반 GC, 임의의 외부 플러그인 실행, 클라우드 공개 endpoint를 넣지 않습니다. 두 클라이언트 공유 상태와 권한 분리가 검증되지 않으면 단순 파일 정리기를 만들었을 뿐, Locus를 검증한 것으로 보지 않습니다.

## 범위 밖

기업용·다중 사용자 조직 모델, Agent-to-Agent 프로토콜, 범용 workflow engine, marketplace, 분산 합의, 자동화의 완전 자율 실행은 현재 범위에 포함하지 않습니다.

## 개발 시작점

[Implementation Plan](docs/implementation-plan.md)의 M0부터 진행합니다. 아직 실제 설치 명령이나 실행 명령은 제공하지 않습니다. 구현 언어와 SDK 버전은 host 연결 spike 이후 결정하고 고정합니다.
