# 9. 천(망토·꼬리)과 털

Tripo 뼈대에는 천용 뼈가 없다. 천은 Unreal Chaos Cloth로 움직인다. Python에는 천 에셋을 만드는 API가 없어서 C++ 에디터 함수 `UNyabloClothTools::SetupSectionCloth`(`reference_impl/unreal/cpp/NyabloClothTools.*`)를 빌드 스크립트에서 부른다.

## 공통: 보이는 천 + 시뮬레이션용 복사본

- 보이는 천은 UV 이음매마다 정점이 나뉘어 있다. 그대로 시뮬레이션하면 수백 조각으로 찢어진다(v2: 560조각).
- 그래서 천마다 정점을 합친 이음매 없는 저해상도 복사본을 따로 슬롯에 둔다(`M_<Name>_ClothSim`, `M_<Name>_TailSim`). 물리는 복사본으로 계산하고 보이는 천이 따라간다. 복사본은 렌더에서 빠진다.
- `SetupSectionCloth(Mesh, RenderSection, SimSection, PinDirection, PinBand, Slope, MaxDistanceCap, AnimDrive, ConfigOverrides)`: 천 조각마다 PinDirection 끝에서 PinBand(cm) 안은 고정, 그 아래는 1cm마다 Slope cm씩 움직일 수 있게(최대 Cap). 몸 충돌은 캐릭터 물리 에셋.

## 망토 (몸과 별도 스켈레탈 메시, 탈착)

망토를 몸 메시에 붙여 만들면 등에 붙은 모양이라 크게 펄럭이지 않고, 벗을 수도 없다. 별도 메시로 만든다.

1. 텍스처: 망토 단독 설정화에서 천만 잘라 쓰고, 어깨 장식 자리는 천으로 메우고, 배경은 투명(찢어진 끝단·구멍)으로 한다. 이미지마다 잘라낼 좌표가 달라서 예시만 둔다: `reference_impl/deathknight/make_cape_tex.py`. 안감은 재질에서 뒷면을 검게 칠한다.
2. 메시:
   ```bash
   blender -b -P $SKILL/scripts/build_cape.py -- --hero SK_<Name>.fbx --tex <망토 텍스처.png> --out <dir> [--top 0.848 --bottom 0.27 --clear 0.018]
   ```
   처리된 주인공(A포즈)의 몸 외곽을 따라 목깃 뒤에서 무릎까지 걸리는 격자다. 위쪽 ±40°(어깨 갑옷 사이)에서 아래로 ±82°까지 넓어져 팔 뒤로 옆구리를 감싼다. 정점마다 자기보다 위에 있는 몸 외곽의 최댓값에 걸린다(튀어나온 곳을 지나 곧게 떨어짐). 보이는 격자 + 시뮬레이션 격자, 가중치는 모두 Spine02.
   출력 이름은 `HeroCape`로 고정돼 있다: `SK_HeroCape.fbx`(슬롯 `M_HeroCape_Cloth`, `M_HeroCape_ClothSim`), `T_HeroCape_BaseColor.png`, `HeroCape.json`. 캐릭터가 여럿이면 도구 안의 이름 문자열을 바꾼다. Unreal 빌드는 `export/characters/HeroCape/`가 있으면 망토를 가져온다.
3. 확인 렌더: `review_cape.py -- <hero fbx> <hero tex> <cape fbx> <cape tex> <out>`(앞·왼쪽·뒤·오른쪽).
4. Unreal(`ue_build_plaza.py` 4b절): 주인공 뼈대로 가져오기(`opt.skeleton`), 주인공 물리 에셋 공유, `M_Cape`(마스크, 양면, `TwoSidedSign`으로 뒷면은 안감 색, `used_with_clothing`), 천 설정 `(Z 위, 고정 4cm, 1cm마다 3cm, 최대 90cm, drive 0)` + `{GravityScale 0.7, Drag 0.3, Lift 0.3, LinearVelocityScale 1, AngularVelocityScale 1}`.
5. 게임 코드(`NyabloHero`): 망토 컴포넌트가 몸의 리더 포즈를 따르고, C키로 켜고 끈다(끄면 천 계산 정지). 공격·달리기 때 캐릭터에 붙인 바람 컴포넌트로 뒤·위로 돌풍을 준다(Chaos Cloth는 월드 바람을 읽는다).

망토 값 조정 기록: 고정 띠 12cm·1cm마다 0.45cm·최대 45cm → 끝자락만 흔들림 → 고정 4cm(목 부분만)·3cm·90cm로 어깨부터 통째로 휘게 했다.

## 꼬리

- 부위 구분에서 꼬리 면을 `M_<Name>_Tail`로 떼고(조립 설정의 `tail` 영역, 또는 몸 뒤쪽 X < −0.102×키·허리 아래), 시뮬레이션 복사본을 만든다.
- 천 설정: 몸 쪽(+X) 6cm 고정, 0.3배, 최대 18cm, **Anim Drive 0.25**(원래 모양으로 되돌리는 힘. 없으면 원통이 찌그러진다).

## 셸 털

```
process_character.py ... --fur-shells 12 --fur-length 0.018
```

- 털 부위 면을 노멀 방향으로 12겹 복제한다(키의 1.8%). 겹 높이는 UV1.x에 넣는다. 천 물리가 걸린 꼬리는 제외한다.
- Unreal `M_FurShell`(마스크): 가닥 높이 무늬 `T_FurStrands`를 UV0에 8회 반복해 깔고, 가닥 높이가 겹 높이보다 높은 곳만 남긴다. 뿌리는 어둡게 한다(`ue_build_plaza.py`의 `build_fur_master`).
- Unreal 그룸(Alembic)은 Blender 내보내기에 가닥별 색이 안 들어가 줄무늬를 살릴 수 없어서 셸 방식을 택했다.
- 효과: 가까이서는 머리·팔 윤곽이 보송해지지만 게임 거리에서는 차이가 작다.

## 합격 기준

- 연속 촬영(`-NyabloBurst`)에서 서 있을 때 늘어지고, 돌거나 베면 망토가 어깨부터 뒤로 휘날린다. 꼬리가 흔들리며 원통 모양을 유지한다.
- 망토가 다리·몸을 뚫지 않는다. 벗으면 망토 부속(붉은 천 등)이 하나도 남지 않는다.

## 알려진 한계

- 망토 천과 꼬리 천은 서로 충돌하지 않는다. 꼬리가 망토를 뚫고 보일 수 있다.
- 적에게는 래그돌용 물리 에셋을 만들지만 주인공에게는 만들지 않았다(`ue_build_plaza.py` 주석: 새 몸 물리 에셋이 망토·꼬리 천과 부딪히기 시작함). 주인공 래그돌이 필요하면 천 충돌을 함께 다시 검증한다.
