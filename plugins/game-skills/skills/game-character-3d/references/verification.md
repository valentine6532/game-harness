# 검수와 도구 목록

## 검수 원칙

1. **사용자가 지적한 것은 같은 구도로 전후를 찍어 확인한다.** 게임 카메라와 근접 카메라, 같은 게임 시각(고정 1/30초 연속 촬영)으로 비교한다. 수치만으로 "고쳤다"고 하지 않는다.
2. **검사 도구의 가정을 먼저 확인한다.** 반지름·방향·축 같은 가정값을 실제 모델에서 잰다. 가능하면 외부 기준(원본 동작의 손가락 뼈, 설정화)과 대조한다.
3. **원인을 단정하기 전에 단계별로 같은 화면을 비교한다.** 생성 원본 → 조립·면 줄이기 → 처리 FBX → 게임을 같은 카메라·단색 조명으로 찍어 어느 단계에서 나빠졌는지 찾는다(예: 게임에서만 번들거림 = 노멀·탄젠트 가져오기 문제였다).
4. 결과 이미지는 `design/<asset>/results/`(또는 프로젝트 규칙)에 남기고 기록 문서에서 링크한다.
5. **부착·파지·동작을 따로 판정한다.** 손가락 접촉의 확대 비교와 정상 속도에서의 검 동작 비교는 다른 검사다. 명중 로그는 판정 확인이며 시각적 자연스러움을 보증하지 않는다. 에디터에서 설정한 애니메이션 샘플이 실제 평가됐는지 자세별 손 뼈 좌표·클립 위치도 확인한다. 손 교체 검수는 [08_hand_grasp.md](08_hand_grasp.md).

## 도구 목록 (`$SKILL/scripts/`)

Blender 도구는 `blender -b --factory-startup -P <도구> -- <인자>`, 그 밖은 시스템 `python`.

**실행 보조**
| 도구 | 용도 |
| --- | --- |
| `nowin.py` | 콘솔·창 없이 외부 프로그램 실행 |
| `winwatch.py` | 새로 뜨는 창과 부모 프로세스 기록(창 원인 추적) |
| `tripo_step.sh` | Tripo 작업 제출 + 장부 기록 |
| `run_codex.sh` | codex 이미지 생성(세션 폴더에서 결과 회수) |

**설정화·생성 검수**
| 도구 | 용도 |
| --- | --- |
| `bg_fill.py` | 설정화 배경을 정확한 #d0d0d0으로 |
| (에이전트가 직접 봄) | 설정화 3/4 틀어짐 검사와 다시 그리기 규칙: [front_check.md](front_check.md) |
| `review_glb.py` | 생성 GLB 정투영 앞·옆·뒤(+확대) |
| `inspect_render.py` | 삼각형·재질·치수 보고 + 여러 방향·와이어프레임 |

**조립·UV·굽기·텍스처**
| 도구 | 용도 |
| --- | --- |
| `sample_points.py` | 통짜 몸 표면 점군(`body_pts.npy`) |
| `assemble_parts.py` | 부위 조립 + 아틀라스 |
| `fix_ghost.py` | 한쪽 텍스처 흠을 반대쪽 색으로 덮기 |
| `bake_normal_onto.py` | 고해상도 → 기존 UV로 노멀만 굽기 |
| `reuv_bake.py` | UV 새로 펼치기 + 색·ORM 옮기기 + 노멀·AO 굽기 |
| `bake_highpoly.py` | 고→저 면 줄이기 + 전체 맵 굽기(초기 방식) |
| `checker_render.py`, `draw_uv_layout.py` | UV 체커 렌더, UV 배치 그림 |
| `classify_parts.py` | Tripo 부위 분리 → 재질 종류 |
| `fix_textures.py` | 칠해진 빛·금속 번짐 보정 |
| `make_glow_mask.py` | 발광 마스크 |
| `render_textured.py` | 구운 게임 메시 텍스처 렌더 |

**리깅·동작**
| 도구 | 용도 |
| --- | --- |
| `process_character.py` | 중심 처리(06_rig_process.md) |
| `exaggerate_attack.py` | 공격 몸 과장(`process_character.py`가 부름) |
| `anim_frames.py` | 모든 동작 프레임 시트 |
| `anim_motion.py`, `hand_speed.py` | 오른손 높이·속도(공격 구간) |
| `tip_path.py` | 칼끝 궤적(적중 프레임) |
| `amp_metrics.py` | 공격 크기(보폭·낮추기·회전·팔 뻗기) |
| `exag_preview.py` | 과장 안 비교 렌더 |
| `pose_jump.py` | 동작 전환 순간 자세 튐 |
| `root_drift.py` | 동작별 Root/Hip 이동량 |
| `impact_profile.py` | 공격 타격감: 적중 뒤 급정지·감속 꼬리·다시 빨라짐(07 "타격감") |
| `game_swing_rhythm.py` | 게임 고정 30fps 로그(`NYABLO_TIP`)로 준비/베기 프레임, 한 타 길이, 칼끝/손 속도비, 대비. 리듬 시안 비교(07 "무기 성격에 맞는 리듬") |
| `mixamo_rest_check.py` | Mixamo 파일 기본 자세가 T자세인지(리타깃 가정 확인) |
| `download_mixamo.py` | 공개 아카이브에서 동작 ID로 Mixamo FBX 받기(시스템 `python`, `requests` 필요) |

**무기·천**
| 도구 | 용도 |
| --- | --- |
| `process_props.py` | 무기·소품 처리(펴기, 칼자루 가늘게, 피벗) |
| `edge_axis.py`, `edge_preview.py` | 날 방향 계산, 전후 잔상 렌더 |
| `swing_lag.py` | 손·칼끝 속도 최고점 시간차와 몸 비틀기·낮춤(막대 느낌 진단, 원본 모션캡처와 비교) |
| `edge_roll_scan.py`, `edge_tilt.py` | 칼 축 둘레 손 회전별 면 기울기 탐색, 면 기울기 측정(`--attack-edge-roll` 각도 결정) |
| `build_cape.py`, `review_cape.py` | 별도 망토 메시, 확인 렌더 |

**기타**: `sheet.py`(렌더 여러 장을 한 장으로).

`reference_impl/history/`에는 쓰지 않는 도구를 기록으로 둔다: `smart_texture.py`(스캔 재질 덧씌우기, 오히려 지저분해짐), `make_textures.py`(배경용 반복 텍스처).

## 게임 검수 수치 (데스나이트 최종)

| 항목 | 값 |
| --- | --- |
| 자동 전투 | 11~15초 안에 적 5명 전멸, 헛친 공격 0 |
| 동작 전환 몸 튐 | 키의 1.2% |
| 프레임당 엉덩이 이동 | 최대 29cm(달리기·파고들기 포함, 40cm 초과 0건) |
| 날 방향 기울기 | 11° |
| 화면 밝기(게임 카메라) | 평균 150~165, 거의 검은 픽셀 3% 미만 |
