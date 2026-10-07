# 6. 리깅과 캐릭터 처리

## Tripo 리깅 (통짜 몸)

```bash
T=$SKILL/scripts/tripo_step.sh
bash $T body/rigged/retopo dk mesh decimate <몸 생성 task id> --quad --face-limit 40000 -p model=v1.0          # 10
bash $T body/rigged/rig    dk anim rig <retopo task id> --rig-type biped --spec tripo --out-format glb -p model=v1.0-20240301   # 25
bash $T body/rigged/anim   dk anim retarget <rig task id> --animation preset:biped:idle preset:biped:run --out-format fbx --animate-in-place   # 10 x 2
```

- **조합은 `v1.0-20240301` + `spec=tripo` + 프리셋 `preset:biped:*`만 된다.** 다른 조합은 리타깃이 실패한다(pitfalls.md).
- 리깅 결과는 `--out-format glb`를 줘도 `model.fbx`로 온다. 뼈 41개(`Root/Hip/L_Thigh/…/R_Hand`), 손가락 뼈 없음. 손가락 뼈가 필요하면(쥐는 방식 B) 08_weapon.md "B. 손가락 뼈 심기"를 따른다(미검증).
- 프리셋 동작: idle·walk·run·dive·climb·jump·slash·shoot·hurt·fall·turn. 근접 공격은 `slash` 하나뿐이고 `shoot`은 구르며 총을 쏘는 동작이다. 공격·대기·달리기는 Mixamo에서 가져온다(07_animation.md). 프리셋 동작은 최소한 첫 동작 FBX가 필요해서 idle·run을 받는다.
- A포즈로 만든 모델이 리깅이 잘 된다(큰 어깨 갑옷은 T포즈에서 팔을 내릴 때 크게 늘어난다).

## `process_character.py`

리그 FBX를 정리해 Unreal용 `SK_<Name>.fbx` + `<Name>.json` + 텍스처를 만드는 중심 도구다. 데스나이트 실행 예: `reference_impl/deathknight/run_dk_process.sh`.

```bash
blender -b --factory-startup -P $SKILL/scripts/process_character.py -- --name Hero \
  --glb body/rigged/rig/.../model.fbx \          # 리그 결과(메시 + 뼈대)
  --fbx body/rigged/anim/.../model.fbx \         # 첫 --fbx는 동작이 든 파일이어야 한다
  --out <abs out> \
  --baked assembly/final \                       # 조립한 부위 메시로 교체, 가중치는 리그 메시에서 옮김
  --parts assembly/final/Hero_parts.glb --parts-json assembly/final/Hero_parts.json \
  --fur-shells 12 --fur-length 0.018 \
  --texfix "--steel-f0 keep --steel-chroma 1.0 --gold-f0 keep" \
  --mixamo <clip>=<file.fbx> ... --rezero ... --exaggerate ... --attack-body ... \   # 07_animation.md
  --fist-hole R:0.00955                          # 08_weapon.md
```

| 옵션 | 하는 일 |
| --- | --- |
| (기본) | 뼈대 + 스킨 메시만 남김(Tripo FBX의 Camera/Cube/Light 제거), 동작 합치기·이름 `<Name>_<clip>`, 루트를 원점으로, 텍스처 추출(노멀 GL→DX), run/walk의 제자리 처리와 지면 속도 기록 |
| `--baked <dir>` | `bake_highpoly.py`나 `assemble_parts.py` 결과로 메시 교체. 리그 메시에 자동 정렬 후 **기본 자세에서** 가중치 전송 |
| `--parts` + `--parts-json` | 면마다 재질 종류(털·천·가죽·금속·꼬리). 천 → `M_<Name>_Cloth`, 꼬리 → `M_<Name>_Tail` + 시뮬레이션용 복사본(`_ClothSim`/`_TailSim`). 천 면이 0개면 천 칸을 만들지 않는다 |
| `--fur-shells N --fur-length L` | 털 면을 노멀 방향으로 N겹 복제(키의 L배), `M_<Name>_Fur`, 겹 높이는 UV1.x |
| `--normal <png>` | 노멀맵 교체(`bake_normal_onto.py` 결과) |
| `--uv <dir> --tex-dir <dir>` | `reuv_bake.py` 결과의 UV·텍스처로 교체 |
| `--texfix "<args>"` | 끝에서 부르는 `fix_textures.py`에 인자 전달 |
| `--cloth-classes <png>` | (v2 방식) 색 지도로 천 면 고르기. 부위 분리가 있으면 쓰지 않는다 |

`<Name>.json`에 들어가는 것: `rest_height_m`, `clips`(프레임 범위, 지면 속도), `textures`, `grip`(08_weapon.md), `lunges`(07_animation.md).

## 내보내기 규칙 (도구에 들어 있음, 바꾸지 말 것)

- FBX 가져오기에서 `ignore_leaf_bones=True`를 쓰면 가중치가 있는 손·머리·트위스트 뼈 11개가 사라진다. 끈다.
- FBX 내보내기는 `mesh_smooth_type='OFF', use_tspace=True`. Unreal 가져오기는 `FBXNIM_IMPORT_NORMALS_AND_TANGENTS` + MikkTSpace. 이렇게 안 하면 Unreal이 노멀·탄젠트를 다시 계산해서 구운 노멀맵과 어긋나고, 게임 화면에서만 털과 얼굴이 어둡고 번들거리며 각져 보인다.
- Tripo FBX의 평면 사용자 지정 노멀은 지우고 smooth로 둔다(각져 보임).
- 키 계산에서 `_Fur`·`Sim` 슬롯을 뺀다(털 겹이 머리 위로 올라와 게임 속 캐릭터가 작아진다).

## 합격 기준

- 가중치 없는 정점 0개, 형태 오차(리그 메시 대비) 0.1% 안팎. 데스나이트: 72,467 정점 모두 가중치.
- `anim_frames.py --input SK_<Name>.fbx --out <dir> --frames 8`로 모든 동작의 팔다리 꺾임·방향 이상 없음.
- 게임 자동 전투에서 부위 이음매가 벌어지지 않는다. 동작 중 몸 튐이 작다(10_unreal.md).

## 실패 사례

- 예전 저해상도 뼈대에 새 고해상도 메시 가중치를 옮기면 형태 차이(평균 4.6%) 때문에 망토·팔이 찢어졌다. 고해상도 작업 자체를 Tripo로 리깅한다(형태 오차 0.09%).
- 동작 중인 자세에서 가중치를 옮기면 조각이 늘어난다. 반드시 기본 자세에서 옮긴다.
