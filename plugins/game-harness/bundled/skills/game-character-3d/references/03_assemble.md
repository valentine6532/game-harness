# 3. 부위 조립

부위별 모델을 통짜 몸의 해당 구간에 맞춰 붙이고, 하나의 메시와 하나의 4K 아틀라스로 합친다. 재질은 하나라서 이후 처리(`process_character.py`)는 통짜 모델과 똑같이 돈다.

## 입력

- 통짜 몸 생성 GLB → 표면 점군:
  ```bash
  blender -b -P $SKILL/scripts/sample_points.py -- body/model/.../model.glb body/body_pts.npy     # 30만 점
  ```
- 부위마다 면 줄인 GLB(`parts/<part>_low/.../model.glb`)와, 원본에서 다시 구운 2K 노멀맵:
  ```bash
  blender -b -P $SKILL/scripts/bake_normal_onto.py -- --high parts/<part>_model/.../model.glb \
      --low parts/<part>_low/.../model.glb --out parts/<part>_low/T_normal2k_dx.png --res 2048
  ```
  면 줄이기의 노멀맵은 1K라서 원본(180만 면급)에서 다시 굽는다.

## 조립 설정 (JSON)

예: `reference_impl/deathknight/final.json`(실제 사용본), 이를 만든 `make_cfg.py`.

```json
{"body_pts": ".../body_pts.npy", "out": ".../assembly/final", "name": "Hero", "atlas": 4096,
 "tail": {"part": "legs", "x_below": -0.07, "z_below": 0.5},
 "parts": [
  {"name": "head", "glb": "...", "quad": [0,0], "init": "top",    "region": {"z": [0.845, 1.0]}, "normal_dx": "..."},
  {"name": "arm_r","glb": "...", "quad": [1,0], "init": "axis",   "region": {"z": [0.42, 0.76], "y": [-1, -0.155]}, "trim": {"above_z": 0.80}},
  {"name": "arm_l","glb": "...", "quad": [1,0], "init": "axis",   "mirror": true, "share_uv_with": "arm_r", "region": {"z": [0.42, 0.76], "y": [0.155, 1]}, "trim": {"above_z": 0.80}},
  {"name": "torso","glb": "...", "quad": [0,1], "init": "top",    "region": {"z": [0.58, 0.87], "y": [-0.2, 0.2]}},
  {"name": "legs", "glb": "...", "quad": [1,1], "init": "bottom", "region": {"z": [0.0, 0.60], "y": [-0.16, 0.16]}}]}
```

- `region`: 통짜 몸에서 그 부위가 차지하는 구간. z는 발에서 잰 키의 비율, y는 미터(+Y = 캐릭터 왼쪽).
- `init`: 초기 맞춤. 머리·몸통은 위 끝, 하체는 아래 끝, 팔은 주축.
- `mirror` + `share_uv_with`: 왼팔은 오른팔을 뒤집어 쓰고 아틀라스 칸을 공유한다.
- `trim`: 부위 모델에서 잘라낼 높이(키 비율). 팔 윗부분이 어깨 갑옷 위로 튀어나와 80% 위를 잘랐다.
- `quad`: 4K 아틀라스의 2K 칸 위치. 부위마다 2K를 준다.
- `tail`: 하체의 뒤쪽 아래(x < −0.07, z < 0.5)를 꼬리로 표시한다(천 시뮬레이션용).

```bash
blender -b -P $SKILL/scripts/assemble_parts.py -- assembly/final.json
```

출력: `<out>/<Name>_low.glb`, `T_<Name>_{BaseColor,Normal,ORM}.png`, `<Name>_bake.json`(→ `process_character.py --baked`), `fit.json`(부위별 배율·평균 거리), `parts.npy`(면마다 부위 번호).

맞춤 방식: 크기 탐색 → 몸→부위 최근접점 ICP(Umeyama 닮음 변환). 부위가 구간보다 커도 된다(가려지는 목, 팔 끝). 몸→부위 거리만 맞춤에 쓴다.

## 텍스처 흠 지우기 (필요할 때)

Tripo가 옆모습 얼굴을 목털에 한 번 더 찍어 두는 경우가 있다. 반대쪽 같은 자리의 색을 거울로 옮겨 굽는다.

```bash
blender -b -P $SKILL/scripts/fix_ghost.py -- <out>/<Name>_low.glb <out>/T_<Name>_BaseColor.png \
  '{"y":[0.008,0.06],"z":[0.815,0.87],"nx_min":0.2,"parts_npy":"<out>/parts.npy","part":0}'
```

원본은 `T_<Name>_BaseColor.pre_ghost.png`로 남는다. 조립을 다시 돌리면 이 파일을 먼저 지운다(새 아틀라스가 새 원본).

## 합격 기준

- `fit.json`의 맞춤 오차(키 대비)가 1% 이하. 데스나이트: 머리 0.33%, 팔 0.59%, 몸통 0.94%, 하체 0.58%.
- 근접 렌더에서 부위 이음매가 갑옷 경계에 숨어 있다. 벌어진 틈이 없다.
- 동작을 입힌 뒤(6단계) 이음매가 벌어지지 않는다.

## 캐릭터마다 다시 잴 것

- `region`(구간 높이·폭), `trim`, `tail` 경계: 통짜 몸을 옆·앞에서 렌더해 갑옷 경계 높이를 잰다.
- `fix_ghost.py`의 상자 좌표: 흠이 있는 자리를 렌더로 찾아 정한다.
