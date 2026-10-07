# 5. 텍스처·PBR

## 맵 규격

- `T_<Name>_BaseColor.png`(sRGB), `T_<Name>_Normal.png`(**DirectX**, Tripo/Blender의 OpenGL에서 초록 채널 반전), `T_<Name>_ORM.png`(R = AO, G = 거칠기, B = 금속성).
- `process_character.py`가 생성 GLB·리그 FBX의 재질 연결을 따라 맵을 꺼내 이 규격으로 쓴다. Tripo 리그 FBX에는 BaseColor만 들어 있어서, Normal·ORM은 생성 GLB에서 꺼내 같은 UV에 연결한다(삼각형 수 일치 확인).

## Tripo 텍스처의 문제와 보정

| 증상 | 원인 | 처리 |
| --- | --- | --- |
| 갑옷이 젖은 플라스틱처럼 번들거림, 코등이가 녹은 밀랍 | 강철 거칠기가 한 덩어리로 0.59 근처, 칠해진 넓은 하이라이트 | `fix_textures.py`: 부위 안의 큰 명암을 걷고 평평한 F0 + 세부 디테일로 다시 만듦. 거칠기도 같은 디테일에서 만듦 |
| 가죽끈·천·틈까지 금속으로 칠함 | Tripo 금속성 맵이 흐린 덩어리 | 금속성 > 0.3이면서 색이 금속다운 텍셀만 금속으로 남김 |
| 털·천이 반사됨 | 금속성이 털(중앙값 0.23)·천(0.17)에도 칠해짐 | `process_character.py`의 `fix_orm_by_class`: 털·꼬리·천·가죽은 금속성 0, 거칠기 최소 0.85/0.9/0.65, 금속은 최소 0.35 |
| 천·가죽에 칠해진 큰 주름 그림자와 얼룩 | 생성 시 조명이 색에 구워짐 | `fix_textures.py --charts <reuv dir>`: 조각·부위 안에서 천 70%, 가죽 40% 걷어냄. 주름은 구운 AO·노멀이 대신 만든다 |
| 무기의 나무·손잡이가 노란 금속 | 무기 아틀라스가 거의 전부 금속 | `fix_textures.py --no-gold`: 따뜻한 갈색은 모두 나무·가죽 |

```bash
python $SKILL/scripts/fix_textures.py <dir> <Name> [--no-gold] [--charts <reuv dir>] [--preview class.png] \
  [--steel-f0 0.18|keep] [--steel-chroma 0.35] [--gold-f0 0.32|keep]
```

- `process_character.py`가 처리 끝에 자동으로 부른다(`--texfix "<추가 인자>"`로 인자 전달).
- 원본은 `<dir>/_texfix_src/`에 둔다. 마지막 출력과 해시가 다르면 새 원본으로 보고 다시 백업한다. 여러 번 돌려도 결과가 같다.
- **캐릭터마다 정할 것**: 흑철처럼 원래 어두운 금속은 `--steel-f0 keep --steel-chroma 1`(기본값이면 흑철이 은백색으로 뜬다). 뼈색·청동 테두리는 `--gold-f0 keep`(기본값이면 밝은 금속이 된다). 데스나이트: `--steel-f0 keep --steel-chroma 1.0 --gold-f0 keep`.
- 효과의 폭은 크지 않다. 남는 번들거림은 대부분 밝은 하늘 조명 탓이다.

## 부위 구분 (재질 종류)

- 통짜 모델 + Tripo 부위 분리: `classify_parts.py --parts segment.glb --textured high.glb --out parts.json`(부위마다 색·금속성 다수결: metal / cloth / leather / darkcloth / fur, 몸 뒤의 털 부위는 꼬리). `process_character.py --parts --parts-json`에 넣는다. 부위 분리가 거칠면 `refine_with_texture`가 면마다 색으로 다시 확인한다.
- 조립한 부위 모델: `assemble_parts.py`가 `Hero_parts.glb/json`을 만든다(머리 = 털, 하체 뒤쪽 아래 = 꼬리, 나머지 = 금속).
- `process_character.py`는 부위 지도를 `T_<Name>_Classes.png`(R 금속, G 가죽, B 천, 검정 털·꼬리)로 저장한다. 엔진에는 넣지 않는다.

## 발광 (룬·보석)

```bash
python $SKILL/scripts/make_glow_mask.py <dir> <Name> [--preview png]    # 채도 높은 푸른 텍셀 -> T_<Name>_Emissive.png
```

Unreal `M_Char`의 `Emissive` 텍스처 × `EmissiveColor`로 넣는다. 처음 값 (0.35, 1.1, 2.6)은 하얗게 날아가서 (0.08, 0.4, 1.3)으로 낮췄다. 마스크가 텍스처의 몇 %인지 확인한다(데스나이트 칼 2.5%).

## 합격 기준

- 같은 근접 카메라의 게임 전후 비교에서 판의 젖은 번들거림과 칠해진 얼룩이 줄었다.
- 금속이 설정화의 색(흑철은 검게, 금은 금색)을 유지한다.
- 털·천에 금속 반사가 없다.

## 하지 말 것

- 부위별 Poly Haven 스캔 재질을 덧씌우는 방식(`smart_texture.py`, Substance 스마트 재질 흉내)은 v2에서 오히려 지저분해졌다(스캔 잡음, 두 번 굽기의 흰 이음매, 과한 금속 반사). 이 도구는 `reference_impl/history/`에 기록용으로만 남긴다. Tripo가 준 텍스처를 기반으로 보정만 한다.
- byte 이미지의 `.pixels`는 이미 sRGB 값이다. 한 번 더 변환하면 채도가 빠진다.
