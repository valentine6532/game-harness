# 2. Tripo 생성

## 전략: 통짜 몸 + 부위별 모델

- **통짜 몸**은 두 가지로 쓴다. (1) 부위를 맞출 틀(`body_pts.npy`), (2) 리깅 뼈대와 스킨 가중치의 출처. 화면에 보이는 메시로는 쓰지 않는다.
- **부위별 모델**(머리·팔·몸통·하체)은 Tripo가 부위를 훨씬 정교하게 그린다. 통짜 머리는 젖은 찰흙처럼 뭉개지고, 부위 머리는 털결·흉터·왕관이 또렷했다. 이득은 해상도보다 형태의 정교함이다.
- 먼저 머리·팔만 만들어 근접 렌더로 통짜와 비교한다. 확실히 낫지 않으면 거기서 부위 생성을 멈춘다(크레딧 절약).
- Tripo 저폴리 직접 출력(`P1`, `v3.1 smart_low_poly`)은 노멀맵이 거의 평평하고 AO가 없어 게임에서 찰흙처럼 보였다. 주인공급은 쓰지 않는다. 적·소품처럼 가까이 보지 않는 것에만 쓴다.

## 명령

모두 `bash $SKILL/scripts/tripo_step.sh <out> <asset> <명령...>`으로 제출한다(창 없음, 장부 기록).

| 용도 | 명령 | 크레딧 |
| --- | --- | --- |
| 4방향 → 고해상도 모델 | `generate multiview-to-model front.png left.png back.png right.png --model tripo-v3.1 -p texture_quality=detailed -p geometry_quality=detailed -p pbr=true [-p orthographic_projection=true]` | 60 |
| 이미지 한 장 → 4방향 | `generate image-to-multiview in.png` | 10 |
| 이미지 한 장 → 모델(무기·소품) | `generate image-to-model in.png --model tripo-v3.1 -p texture_quality=detailed -p geometry_quality=detailed -p pbr=true` | 60 |
| 면 줄이기(삼각형, 텍스처 유지) | `mesh decimate <생성 task id> --face-limit N -p model=v1.0` | 10 |
| 면 줄이기(쿼드, 리깅용) | `mesh decimate <생성 task id> --quad --face-limit 40000 -p model=v1.0` | 10 |
| 부위 분리(분류용, 선택) | `mesh segment <생성 task id> --model v2.0-20260430 -p segmentation_granularity=detailed` | 40 |
| 리깅·프리셋 동작 | 06_rig_process.md | 25 + 10/동작 |

- 입력 순서는 정면·왼쪽·뒤·오른쪽이다. 데스나이트 몸은 1024×1536 그림을 1536 정사각으로 여백을 붙여 넣었고(`in_*.png`), `-p orthographic_projection=true`를 줬다.
- 면 줄이기는 **원본 생성 작업의 task id**에 건다. `model=v1.0`이면 Tripo가 색(4K)·거칠기·금속성(2K)·노멀(1K)을 새 메시로 옮겨 준다. 노멀은 1K뿐이라 04_uv_bake.md에서 다시 굽는다.
- 면 수(데스나이트): 머리 1.5만, 팔 1만, 몸통·하체 2.5만 삼각형, 통짜 몸(리깅용) 쿼드 4만, 칼 8천 삼각형. CLI 도움말은 삼각형 2만·쿼드 1만이 상한이라고 하지만 쿼드 4만이 실제로 됐다(쿼드 3만 8,599개).
- 생성 GLB는 Blender에서 +X를 보고, 왼쪽이 +Y이며, 원점 중심이다.

## 검수

```bash
blender -b -P $SKILL/scripts/review_glb.py -- <model.glb> <out prefix>     # 정투영 앞·옆·뒤, 자체 재질
blender -b -P $SKILL/scripts/inspect_render.py -- --input <model.glb|fbx> --out <dir>  # 삼각형·재질·치수 + 와이어프레임
```

## 합격 기준

- 꼬리 1개, 전체 비율이 설정화와 같다. 양손 주먹에 칼자루 구멍이 뚫려 있다(확대 렌더로 확인).
- 부위 모델은 근접 렌더에서 통짜 몸의 같은 부위보다 확실히 또렷하다.
- 옆모습 얼굴이 목털에 한 번 더 찍혀 있지 않은지 본다(Tripo 멀티뷰의 흔한 흠, 03_assemble.md의 `fix_ghost.py`).
- 금속·천 재질이 번들거리는 것은 이 단계의 불합격 사유가 아니다(05_texture.md에서 처리).

## 실패 사례

- 면 줄이기를 부위 분리 결과에 걸면 서버에서 실패한다(환불). 원본 생성 작업에 건다.
- `tripo model texture`는 리토폴로지 결과에 쓸 수 없다("reference_image_path not found", 환불).
- 한 장짜리 이미지로 만든 칼은 칼날이 두께 방향으로 휘어 나온다(5.2cm). 08_weapon.md의 `straighten`으로 편다.
- Tripo 통(barrel)은 저폴리 변환 중 윗면·널판에 구멍이 생겼다. 단순한 회전체 소품은 Blender로 만드는 편이 낫다.
