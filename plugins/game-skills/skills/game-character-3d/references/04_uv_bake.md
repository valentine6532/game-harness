# 4. UV·노멀·AO 굽기

## 무엇을 쓰나

| 상황 | 방법 | 도구 |
| --- | --- | --- |
| 면 줄이기 결과의 노멀이 1K뿐 | 원본 고해상도에서 노멀만 다시 굽기(색·거칠기·금속성은 Tripo 것 유지) | `bake_normal_onto.py` |
| Tripo UV가 수천 조각(부스러기)이라 이음매·밉맵 번짐이 보임 | UV를 새로 펼치고 색·ORM은 옮기고 노멀·AO는 원본에서 굽기 | `reuv_bake.py` |
| 면 줄이기 없이 고해상도 한 덩어리만 있음 | 고→저 굽기(면 줄이기·UV 재배치·노멀·AO·색·거칠기·금속성) | `bake_highpoly.py` (초기 방식) |

데스나이트는 부위마다 `bake_normal_onto.py`로 2K 노멀을 다시 구워 조립했다(03_assemble.md). `reuv_bake.py`는 v4 주인공(통짜 모델 + Tripo 부위 분리 GLB)에서 검증했고, 조립한 데스나이트에는 아직 쓰지 않았다(머리 UV가 잘게 쪼개진 채다).

**조립한 캐릭터에는 부위 분리 GLB가 없다.** `assemble_parts.py`는 면마다 부위 번호(`parts.npy`)를 내지만 `reuv_bake.py --parts`는 GLB를 받는다. 조립 캐릭터의 UV를 새로 펼치려면 `reuv_bake.py`가 `parts.npy`(또는 `Hero_parts.glb`의 부위별 조각)를 조각 기준으로 받게 고쳐야 한다(미구현). 고칠 때는 `process_character.py --baked`가 조립 메시를 리그 메시에 정렬한 뒤의 면 순서와 `parts.npy`의 면 순서가 같은지부터 확인한다.

## 노멀만 다시 굽기

```bash
blender -b -P $SKILL/scripts/bake_normal_onto.py -- --high high.glb --low retopo.glb|fbx --out T_<Name>_Normal.png [--res 4096]
```

- 저해상도 메시는 게임 내보내기와 같은 음영(사용자 지정 노멀 삭제, smooth)으로 굽는다. 그래야 Unreal의 FBX 노멀 + MikkTSpace 탄젠트와 맞는다.
- 얇은 부분에서 빗나간 광선이 만든 거의 수평인 노멀은 평평하게 되돌린다(흰 반점 제거).
- 출력은 DirectX(초록 채널 반전)다. `process_character.py --normal <png>`로 교체한다.

## UV 새로 펼치기

```bash
blender -b -P $SKILL/scripts/reuv_bake.py -- --rig <rig 또는 동작 FBX> --parts <segment.glb> --high <high.glb> \
  --src-dir <원래 텍스처 폴더(_texfix_src 원본)> --name Hero --out <abs dir> \
  --split-by shorter --split-threshold 0.06 --margin 0.003 --head-weight 2 --hand-weight 1.3 --facing-weight 1.15 0.85
```

1. 조각 = Tripo 부위 분리 부위. 60면 미만 부스러기는 이웃에 붙인다.
2. 부위마다 원판이 되도록 자른다(tree-cotree). 주먹 구멍·벨트 같은 고리는 가장 싼 경로로 자르고, 절단선은 등·아래쪽으로 보낸다.
3. `MINIMUM_STRETCH`로 펼친다(찌그러지는 조각은 `ANGLE_BASED`로 다시). 텍셀 밀도가 고르지 않은 조각은 둘로 나눠 다시 펼친다.
4. 색·ORM: 같은 메시에서 옛 UV → 새 UV로 옮긴다(Cycles EMIT, 광선 오차 없음). 노멀·AO: 고해상도에서 새 UV로 굽는다. ORM.R = 0.4 + 0.6 × AO(AO를 100% 쓰면 털이 거의 검게 보인다).

적용: `process_character.py --uv <dir> --tex-dir <dir>`. 리그 메시의 UV를 `uv_new.npy`로 바꾸고, 같은 FBX를 같은 옵션으로 가져오므로 루프 순서가 같다(`loop_verts.npy`로 검사).

검수:
```bash
blender -b -P $SKILL/scripts/checker_render.py -- <rig fbx> <uv_new.npy> <out prefix>   # 체커로 앞·뒤·옆
python $SKILL/scripts/draw_uv_layout.py <reuv dir> <out.png> [uv_new|uv_old] [texture.png]
```

## 합격 기준 (v4 주인공에서 쓴 값)

- 조각 수: 2,381 → 100~160개.
- 얼굴 텍셀 밀도 ≥ 몸통 중앙값 × 1.5.
- 밀도 0.35 미만인 면적 < 1%.
- 정면 체커에서 머리 칸이 몸통 칸보다 작거나 같다. 한 점으로 모이는 곳이 없다.
- 텍스처 사용률 55% 이상이 목표지만, 늘어짐을 없애는 쪽과 부딪치면 늘어짐을 우선한다(v4: 50.2%).
- 게임 근접 화면에서 이음매 끊김·늘어짐이 보이지 않는다.

## 한계

- 색 텍스처는 Tripo 원본 UV에서 옮겨 오므로 원본 해상도 이상은 생기지 않는다. 새로 굽는 노멀·AO만 이득을 본다. 얼굴을 더 또렷하게 하려면 머리를 부위로 따로 생성한다(02_tripo.md).

## 실패 사례

- 작은 조각을 이웃에 붙이기만 하는 방식: 401조각이 됐지만 톱니 같은 가장자리, 나뭇가지 모양 조각, 텍스처 사용률 27%.
- Smart UV Project: 8,500조각. Quadriflow: 이 메시에서 실패.
- 분할 기준 6%를 면 방향(`normal`)으로 자르면 너덜너덜한 망토 끝이 빗살 모양으로 잘려 사용률이 45%로 떨어졌다. `--split-by shorter`로 해결했다.
- `--align-rotation`은 효과가 없었다.
- Blender `Image.save()`는 상대 경로면 파일을 쓰지 않고도 오류를 내지 않는다. 출력 경로는 항상 절대 경로로 준다.
