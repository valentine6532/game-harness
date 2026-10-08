---
name: game-character-3d
description: 설정화 이미지로 게임용 3D 캐릭터·몹·NPC·무기·소품을 끝까지 만든다. 시작할 때 품질 단계(A 주인공·보스 / B 정예 몹·주요 NPC / C 일반 몹·소품·건물)를 묻고 단계에 맞는 공정만 진행한다. A단계 전체 공정은 codex 이미지 생성으로 4방향·부위 설정화 → Tripo 생성(통짜 몸·부위별·무기)과 면 줄이기 → Blender 부위 조립, UV 다시 펼치기, 노멀·AO 굽기, PBR 텍스처 보정 → Tripo 리깅, Mixamo 동작 리타깃과 공격 동작 과장 → 무기 쥐기·날 방향, 망토·꼬리 천, 털 → Unreal 가져오기·재질·천·게임 검증까지 진행한다. 캐릭터·몹·NPC·무기·소품 3D 제작, Tripo 모델 품질 개선, 리깅·동작·칼 쥐기·망토 문제 수정 요청에 사용한다. 이미지만 편집하거나 절차 설명만 원하면 사용하지 않는다.
---

## 프로젝트 오버라이드와 전역 원본 보호

이 스킬은 game-harness가 관리하는 전역 원본이다. 실행 전에 `~/.agents/game-harness/global_runtime.py`로 다음을 실행한다(사용 가능한 Python 실행 파일을 사용한다).

```text
python <사용자 홈>/.agents/game-harness/global_runtime.py prepare skill game-character-3d --project <현재 프로젝트 또는 작업 폴더>
```

명령이 반환한 `project`를 프로젝트 루트로 사용하고 `instructions`를 읽는다. 파일이 없으면 `.game-harness/overrides/skills/game-character-3d/override.md`에 빈 템플릿만 만들어진다. 사용자 요청을 우선하고, 로컬에서 명시한 항목만 기본 지침에 덮어 적용한다. 빈 템플릿은 동작을 바꾸지 않는다. 지정되지 않은 항목과 관련 자료는 기본 지침을 유지한다. 지침 변경은 실행 코드 자체를 변경하지 않는다.

전역의 문서·스크립트·설정·에이전트를 수정하거나 삭제하지 않는다. 새 발견·실험 기록·프로젝트 설정은 프로젝트 폴더에 남긴다. 다른 에이전트를 호출할 때 `project`의 절대 경로와 적용한 오버라이드 경로를 전달하고, 그 에이전트도 자신의 오버라이드를 준비하게 한다. 명령 실패 시 원인을 알리고 준비가 되기 전 작업을 진행하지 않는다. 공통 원본 개선은 설치본 대신 원본 저장소에서 한다.

# 게임 캐릭터 3D 제작 (Tripo + Blender + Unreal)

냐블로 프로젝트에서 주인공 고양이 데스나이트를 만들며 검증한 전 과정이다. 목표 품질은 PC 쿼터뷰 ARPG에서 근접 화면까지 버티는 수준(디아블로 4 기준)이고, 엔진은 Unreal 5.8이다. 각 단계는 **입력 → 명령 → 합격 기준 → 실패 사례** 순서로 `references/`에 있다.

`$SKILL`은 이 파일이 있는 폴더다. 도구는 `$SKILL/scripts/`에 있고, Blender 도구는 `blender -b --factory-startup -P <도구> -- <인자>`로 돈다. 처음이면 [setup.md](references/setup.md)부터 읽는다.

## 0. 품질 단계 정하기 (시작 전에 묻는다)

에셋마다 크레딧을 쓰기 전에 사용자에게 어느 단계인지 묻는다. 요청에 이미 단계가 드러나 있으면(예: "주인공", "배경 소품") 짐작한 단계를 말하고 확인만 받는다. 기준은 장르가 아니라 **카메라 거리 × 화면에 보이는 시간 × 동시에 보이는 수**다.

| 단계 | 대상 | 진행 | 상태 |
| --- | --- | --- | --- |
| A | 주인공, 큰 보스(드래곤 등): 가까이, 오래 본다 | 아래 1~10단계 전체 | 검증됨(데스나이트) |
| B | 정예 몹, 주요 NPC: 중간 거리 | 1(원안 → 정면 → 4방향, 부위 설정화 생략) → 2(통짜 몸 4방향 생성 1번 + 면 줄이기) → 4(노멀 다시 굽기) → 5 → 6 → 7(과장은 선택) → 8(무기가 있으면) → 10. 부위 조립(3)·천·털(9) 생략 | 미검증 |
| C | 일반 몹, 소품, 건물: 멀리, 많이 | 소품·건물: 한 장 그림 → 한 장으로 생성(02의 저폴리 직접 출력도 허용) → 피벗·크기 정리 → 10. 사람형 몹: B에서 다시 굽기(4)·과장도 생략한다. 동작은 같은 Mixamo 원본 파일을 쓰되 몸마다 `process_character.py --mixamo`로 다시 리타깃한다(Tripo 뼈대는 몸마다 달라서 리타깃 결과를 복사할 수 없다) | 미검증 |

- B·C를 고르면 "아직 이 단계로 끝까지 만들어 본 적 없다"고 먼저 알리고 시험으로 진행한다. 끝나면 걸린 시간·크레딧·문제를 프로젝트의 `.game-harness/overrides/skills/game-character-3d/experiments.md`에 적는다. [backlog.md](references/backlog.md)는 읽기 전용 참고다. 검증된 공통 개선은 원본 저장소에서 반영한다.
- 크레딧 추정은 A단계만 있다(약 400~450, 02_tripo.md). B·C는 단계 시작 전에 예상 크레딧을 계산해 보고한다.

## 단계

| # | 단계 | 결과 | 참조 |
| --- | --- | --- | --- |
| 1 | 설정화: 디자인 → 4방향 A포즈 시트 → 부위별 설정화, 무기·망토 단독 | 3D 입력 이미지 | [01_concept.md](references/01_concept.md) |
| 2 | Tripo 생성: 통짜 몸(리깅 뼈대용), 부위별 모델, 무기, 면 줄이기 | 고해상도 GLB, 게임 GLB | [02_tripo.md](references/02_tripo.md) |
| 3 | 부위 조립: 부위를 통짜 몸에 맞춰 하나의 메시·4K 아틀라스로 | `<Name>_low.glb` + 텍스처 | [03_assemble.md](references/03_assemble.md) |
| 4 | UV·굽기: 노멀 다시 굽기, UV 새로 펼치기, AO | 깨끗한 UV, 4K 노멀·AO | [04_uv_bake.md](references/04_uv_bake.md) |
| 5 | 텍스처·PBR: 칠해진 빛 걷기, 금속 정리, 부위 구분, 발광 | BaseColor·Normal(DX)·ORM | [05_texture.md](references/05_texture.md) |
| 6 | 리깅·처리: Tripo 리깅, 가중치 옮기기, `process_character.py` | `SK_<Name>.fbx` + `<Name>.json` | [06_rig_process.md](references/06_rig_process.md) |
| 7 | 동작: Tripo 프리셋, Mixamo 받기·리타깃, 공격 구간·과장, 무기 성격별 리듬(쾌검/둔기)·타격감 | 동작 클립, 공격 구간 표 | [07_animation.md](references/07_animation.md) |
| 8 | 무기: 쥐는 방식(A 주먹 구멍 / B 손가락 뼈), 칼 처리, 쥐는 방향, 손목 보정, 날 방향 | `SM_<Weapon>.fbx`, `grip` | [08_weapon.md](references/08_weapon.md), 손 교체·고정 파지는 [08_hand_grasp.md](references/08_hand_grasp.md) |
| 9 | 천·털: 망토(별도 메시), 꼬리 천, 셸 털 | 천 시뮬레이션 설정 | [09_cloth_fur.md](references/09_cloth_fur.md) |
| 10 | Unreal: 가져오기, 재질, 천, 무기 부착, 동작 섞기, 게임 검증 | 플레이 가능한 캐릭터 | [10_unreal.md](references/10_unreal.md) |

아직 검증 안 된 개선안(쥐기·동작 가설, 품질 단계, 다음 실험 순서)은 [backlog.md](references/backlog.md)에 있다. 작업을 시작할 때 확인하고, 전후 비교로 확인된 것만 본문으로 옮긴다.

검수 방법과 도구 전체 목록은 [verification.md](references/verification.md)에 있다. **이미 겪은 실패와 그 원인은 [pitfalls.md](references/pitfalls.md)에 모여 있다. 새 캐릭터를 시작하기 전에 한 번 읽는다.**

손가락이 칼자루를 감싸는 **파지**와 칼을 휘두르는 **동작 품질**은 따로 판정한다. 2026-09-30 기존 엔진 뼈대를 보존한 오른손 교체·손가락 15개·고정 파지는 사용자가 확인했다. 경계 프레임·날 방향・팔과 칼의 각도 보정 뒤에도 준비와 검 동작 불만이 남았다. 팔을 계속 다시 설계했지만 모두 거절됐다. **원인은 팔·손목을 몸과 따로 재작성한 것이었다.** 모션캡처 팔로 되돌리고, 날 방향은 칼 축 둘레의 일정한 손 회전(`--attack-edge-roll`)으로만 맞추자 사용자가 확인했다([08_hand_grasp](references/08_hand_grasp.md) 5절 "먼저 할 것"). 칼을 휘두르는 동작에서는 원본의 손·칼끝 시간차를 지키고, 몸 과장만 몸통·다리에 얹는다. 잡기/놓기 구현은 아직 검증하지 않았다.

## 반드시 지킬 것

1. **창 없이 실행한다.** 사용자는 작업 중 같은 PC로 다른 일을 한다. Blender·Unreal·Tripo·codex·Build.bat처럼 콘솔이나 창을 띄우는 프로그램은 모두 `pythonw $SKILL/scripts/nowin.py <exe> ...`로 실행한다. `UnrealEditor.exe`에는 `-RenderOffScreen`을 붙인다.
2. **Tripo 크레딧.** 사용자가 정한 상한 안에서만 쓰고, 단계마다 사용량과 잔액을 보고한다. 모든 태스크 ID는 장부(`tripo_ledger.jsonl`)에 남긴다(`scripts/tripo_step.sh`가 자동으로 남긴다). 시간 초과나 재부팅 뒤에는 새로 제출하지 말고 `tripo task get <id>`로 결과부터 받는다. 새 캐릭터 하나에 약 400~450크레딧이 든다(02_tripo.md의 표).
3. **"고쳤다"는 같은 구도의 전후 비교를 본 뒤에만 말한다.** 수치 검사가 통과해도 검사 도구의 가정(크기·방향·기준)이 틀릴 수 있다. 가정을 실제 데이터로 먼저 확인하고, 가능하면 원본 동작이나 설정화 같은 외부 기준과 대조한다. 보고에는 게임 캡처를 근거로 붙인다.
4. **캐릭터마다 다시 재야 하는 값이 있다.** 공격 구간과 적중 프레임, 주먹 구멍 반지름, 쥐는 방향, 날 방향, 부위 조립 영역, 천·꼬리 경계, 금속 밝기 옵션 등이다. 각 단계 문서의 "캐릭터마다 다시 잴 것"을 따른다. `reference_impl/deathknight/`의 숫자를 그대로 쓰지 않는다.
5. **원본과 이전 결과를 지우지 않는다.** 교체 전에 `_<name>_backup/`로 백업하고, 되돌리는 방법을 기록한다. 텍스처 보정 도구는 원본을 `_texfix_src/`에 둔다.
6. **Unreal 에디터가 열려 있으면 빌드하지 않는다.** 저장이 거부되거나 C++ 빌드가 Live Coding 때문에 막힌다. `tasklist`로 확인하고, 열려 있으면 사용자에게 닫아 달라고 한다.
7. **결과물은 게임에서 조작할 수 있어야 한다.** 장면 한 장만 만들고 끝내지 않는다. 범위를 줄였다면 먼저 말한다.
8. **기록한다.** 프로젝트의 제작 기록 문서에 절을 추가한다: 사용자 지적 → 원인(측정) → 수정 → 결과(전후 이미지) → 되돌리기 → 남은 것.

## 폴더 (권장)

```
workspace/<asset>/
  concepts/        설정화, 프롬프트(.txt), codex 출력
  body/            통짜 몸 입력(in_*.png), model/, rigged/{retopo,rig,anim}/, body_pts.npy
  parts/           <part>_model/, <part>_low/ (면 줄이기 + T_normal2k_dx.png)
  assembly/        <tag>.json(조립 설정), final/(조립 결과)
  sword/ cape/     무기·망토
  tripo_ledger.jsonl
export/characters/<Name>/   SK_<Name>.fbx, <Name>.json, T_<Name>_*.png   (Unreal 빌드가 읽는 곳)
export/props/               SM_<Weapon>.fbx, T_<Weapon>_*.png
```

## 참고 구현

`reference_impl/`은 데스나이트에 실제로 쓴 파일이다. 그대로 실행하지 말고 읽고 옮겨 쓴다.
- `deathknight/`: 처리·조립 실행 스크립트, 조립 설정 예(`final.json`, `make_cfg.py`), 칼 설정(`sword_spec.json`), codex 프롬프트 예(`prompts/`), 망토 텍스처 예(`make_cape_tex.py`).
- `unreal/python/`: 레벨 빌드 스크립트(`ue_build_plaza.py`: 캐릭터 가져오기·재질·천·무기 부착), 촬영.
- `history/`: 쓰지 않기로 한 도구(스캔 재질 덧씌우기 등).
- `unreal/cpp/`: 천 설정(`NyabloClothTools`), 동작 섞기(`NyabloAnimInstance`), 무기·검 궤적·공격 구간(`NyabloCharacter`), 망토 탈착·자동 검증(`NyabloHero`).

`scripts/`의 도구는 2026-09-28 냐블로 프로젝트(`workspace/plaza_v2/tools`, `workspace/deathknight/tools`)에서 복사했다. 이 스킬의 도구로 데스나이트를 다시 처리해 설치본과 같은 결과(텍스처·Hero.json 해시 일치, 동작 자세 차이 0)가 나오는 것을 확인했다. 새 캐릭터 전체를 이 문서만 보고 처음부터 만들어 본 적은 아직 없다.
