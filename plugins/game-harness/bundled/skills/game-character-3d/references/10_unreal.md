# 10. Unreal 설치와 게임 검증

참고 구현: `reference_impl/unreal/python/ue_build_plaza.py`(커맨드릿으로 레벨 전체를 다시 만든다), `reference_impl/unreal/cpp/`. 냐블로 프로젝트 전용 코드라 그대로 돌리지 말고 필요한 부분을 옮긴다. 아래는 캐릭터에 필요한 부분의 위치와 규칙이다.

## 프로젝트 준비

- C++ 모듈이 필요하다. 천 에셋 생성(`NyabloClothTools`, 에디터 전용)과 동작 섞기(`NyabloAnimInstance`)는 Python으로 못 만든다. `Build.cs`에 `ClothingSystemRuntimeCommon`, `ClothingSystemRuntimeInterface`, 에디터 빌드에 `ClothingSystemEditorInterface`, `UnrealEd`.
- C++ 빌드: `pythonw nowin.py "$UE_ROOT/Engine/Build/BatchFiles/Build.bat" <Project>Editor Win64 Development -Project=<uproject>`. **에디터가 열려 있으면 Live Coding 때문에 거부된다.** 1~20분 걸린다.
- 레벨 빌드: `pythonw nowin.py UnrealEditor-Cmd.exe <uproject> -run=pythonscript -script=<build.py> -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput`. 에디터(`UnrealEditor.exe`)가 떠 있으면 빌드 스크립트가 아무것도 안 하고 멈추게 해 둔다(`BUILD_ABORTED`). 텍스처·FBX가 그대로면 가져오기를 건너뛰는 모드(`NYABLO_SKIP_IMPORT=1`, 약 40초)를 쓴다.
- 렌더: DX12 + SM6(가상 섀도 맵), 조명 Movable + `r.AllowStaticLighting=False`(Lumen만). 안 하면 에디터에 SM6 경고·"라이팅 다시 빌드" 팝업이 뜬다.

## 캐릭터 가져오기 (`ue_build_plaza.py` 4절 "characters")

- `FbxImportUI`: skeletal, 동작 포함, 재질·텍스처 가져오기 끔, `import_uniform_scale = 목표 키(m) / <Name>.json rest_height_m`(동작도 같은 배율).
- **`normal_import_method = FBXNIM_IMPORT_NORMALS_AND_TANGENTS`, `normal_generation_method = MIKK_T_SPACE`.** 구운 노멀맵과 맞추기 위해서다.
- 텍스처: 노멀은 `TC_NORMALMAP`, ORM은 `TC_MASKS`(sRGB 끔).
- 다시 가져올 때 FBX 재가져오기는 기존 AnimSequence를 덮어쓰지 않고 새 동작도 만들지 않는다. `/Game/Characters`를 지우고 새로 가져온다. 맵은 지우지 말고 열어서 액터를 비운 뒤 다시 채운다(지운 패키지가 메모리에 남아 `new_level`이 실패).
- 래그돌용 물리 에셋: `FbxImportUI.create_physics_asset`은 커맨드릿에서 아무것도 만들지 않는다. `SkeletalMeshEditorSubsystem.create_physics_asset(sk, True)`로 만든다.
- 천: 슬롯 이름으로 보이는 천·시뮬레이션 복사본 섹션을 찾아 `NyabloClothTools.setup_section_cloth(...)`(09_cloth_fur.md).
- 동작 재생 속도: `<Name>.json` clips의 `ground_speed_heights_per_s × 키 × 100`(cm/s) → 이동 속도에 맞춘 재생 배속.

## 재질 `M_Char` (`build_masters`)

- BaseColor × `Tint`, Normal, ORM(R AO, G 거칠기, B 금속성), `Emissive` 텍스처 × `EmissiveColor`(룬 발광).
- 반사 = `Specular × (1 − 거칠기)`: 거친 털·천에는 반사가 거의 없고 금속은 금속성이 정한다(털 끝의 푸른 번들거림 제거).
- 피격 번쩍임은 Custom Primitive Data[0]("Flash")로(동적 재질 복제 없음).
- **`used_with_skeletal_mesh = True`를 저장한다.** 안 하면 에디터에서는 정상인데 `-game`에서 캐릭터가 전부 기본 회색 재질로 바뀐다(로그: `missing usage flag SkeletalMesh`).
- 털: `M_FurShell`(`build_fur_master`), 망토: `M_Cape`(마스크·양면·안감).

## 무기 부착

- 기존 캐릭터의 손만 교체할 때는 [08_hand_grasp.md](08_hand_grasp.md)처럼 실제 엔진 기준 자세를 보존한 임포트를 검토한다. 손가락 추가만으로 전체 Characters 폴더 삭제·몸 클립 재생성을 요구하지 않는다. 새 재질 슬롯 때문에 천 섹션 번호가 달라지면 보이는 천/시뮬레이션 섹션 연결을 복구한다. 전체 생성기가 별도 설치를 덮어쓰는지도 기록한다.

- `grip_relative`(08_weapon.md): 기본 자세에서 계산한다. 계산하는 동안 대기 동작을 잠시 빼서 참조 자세로 둔다(전투 대기 자세에서 재면 칼이 손목에 붙는다).
- 손 소켓 스케일로 상대 위치를 나눈다. 무기 컴포넌트는 Movable.

## 공격 데이터와 동작 섞기

- 공격 한 타(`FNyabloAttackClip`): `Anim`, `Start/Strike/Hit/EndFraction`(07_animation.md의 s/k/h/e를 `(frame−1)/(last−1)`로), `PlayRate`, `WindupRate`(준비는 느리게), `StrikeRate`(내려치기는 빠르게), `DamageScale`, `Lunge`(`<Name>.json` lunges, 휘두르기가 끝나면 캡슐 이동).
- 적중 뒤 구간(h → e): `FollowFrames`(적중 뒤 이어가기 원본 프레임 수), `FollowRate`, `HoldSeconds`(뻗은 자세 버팀), `RecoverRate`. 준비 꼭대기 모으기는 `ApexFrames`(베기 직전 원본 프레임 수)·`ApexRate`. 쾌검은 `FollowRate`=베기 배속, 버팀·모으기 0(07 "무기 성격에 맞는 리듬"). 버팀은 역경직과 별개다.
- 맵을 바꾸지 않는 시안 실행 인자(한손 콤보 클립만): `-NyabloWindup= -NyabloStrike= -NyabloApexFrames= -NyabloApexRate= -NyabloFollowRate=`, 모든 클립 `-NyabloHold= -NyabloFollow= -NyabloRecover=`(회복은 PlayRate 배수). `-NyabloTipLog`의 `NYABLO_TIP`에 칼끝(`speed`)과 손(`hand`) 이동량이 있다.
- 이동 취소(2026-10-01): 공격을 시작한 뒤 새로 누른 이동 입력은 준비·베기 어디서든 공격을 끊고 이동으로 넘어간다(`ANyabloHero::TryMoveCancel` → `ANyabloCharacter::CancelAttack`). 이동키를 누른 채 공격을 시작했다면 예전처럼 적중 후 `RecoveryCancelDelay`가 지나야 끊는다(안 그러면 달리며 누른 공격이 바로 사라짐). 스킬은 적중 전 취소 불가(쿨타임 낭비 방지). 끊을 때 캡슐을 **실제로 그려진 엉덩이 아래로** 옮긴다(`HipInActorSpace() − HipAtAttackStart`). 베기 중에는 엉덩이가 캡슐보다 최대 약 1m 앞에 있어서, 구간 비율로 추정하거나 상한을 두면 몸이 앞에 남고 다음 공격이 방향을 틀 때 크게 튄다(134cm 측정). 시험: `-NyabloCancelAt=<초>`(자동 전투가 매 일반 공격 그 시점에 이동 입력), 로그 `NYABLO_CANCEL`.
- 동작 섞기(`UNyabloAnimInstance`): 애니메이션 블루프린트 없이 프록시가 두 동작을 뽑아 섞는다. 섞는 도중 새 동작이 오면 마지막에 그린 자세를 저장해 두고 거기서 섞는다(한쪽 동작을 기준으로 하면 10~21% 튐). 캡슐이 보폭만큼 따라잡을 때 섞이는 동작들의 루트를 반대로 옮긴다(`ShiftRoots`). 페이드아웃하는 공격은 구간 끝 + 0.1초까지만 재생한다(`MaxTime`). 섞는 시간: 이동→공격 0.09초, 같은 콤보 0.08초, 마무리↔콤보 0.18초, 공격→대기·달리기 0.2초.
- 메시는 액터 Tick 뒤에 자세를 계산한다(`AddPrerequisite`). 안 하면 옮긴 캡슐 위에 이전 자세가 한 프레임 남는다.
- 검 궤적(`TrailVFX`)은 무기 컴포넌트에 붙어서 칼과 함께 돈다. 내려치기 시작에 켜고 적중 뒤 끈다.

## 게임 검증

```bash
pythonw nowin.py UnrealEditor.exe <uproject> -game -windowed -ResX=1280 -ResY=720 -RenderOffScreen -nosplash \
  -NyabloAuto [-NyabloBurst -UseFixedTimeStep -FPS=30 -NyabloBurstStart=2.6 -NyabloBurstStep=0.0333 -NyabloBurstCount=60] \
  [-NyabloCamDist=420 -NyabloCamPitch=-15] -log -abslog=<log>
```

- `-NyabloAuto`: 주인공이 가장 가까운 적에게 가서 베고, 정해진 시각에 스크린샷(`Saved/Screenshots/WindowsEditor/`), 21초에 종료. 로그에 적 전멸 시간, HP, 프레임당 엉덩이 튐, 동작 전환 자세 튐을 남긴다. 새 프로젝트에는 같은 자동 검증 모드를 먼저 만든다(`NyabloHero::AutoDrive` 참고).
- 동작 확인은 게임 시간을 1/30초로 고정한 연속 촬영(`-UseFixedTimeStep -FPS=30` + 촬영 간격 0.0333)으로 한다. 느린 스크린샷 때문에 게임 시간이 건너뛰지 않는다.
- 근접 비교는 `-NyabloCamDist=420 -NyabloCamPitch=-15`. 기본 게임 카메라(21m)도 함께 본다. 두 카메라에서 보이는 것이 다르다(예: 칼 두께 차이는 기본 거리에서 거의 안 보임).
- 새 4K 텍스처를 가져온 직후 에디터 촬영은 셰이더 컴파일로 초당 3프레임이 되어 스크린샷이 저장되지 않는다. 게임 모드로 찍는다.

## 합격 기준

- 자동 전투: 적 전멸, 헛친 공격 0, 동작 전환 몸 튐 키의 2% 이하, 부위 이음매 벌어짐 없음.
- `-game` 로그에 `missing usage flag` 0건.
- 사용자가 지적한 문제는 같은 카메라·같은 순간의 전후 비교에서 사라졌다.

## 실패 사례

- `-ExecutePythonScript`는 스크립트 직후 에디터를 닫는다. 에디터에서 스크립트를 돌리려면 `-ExecCmds="py <스크립트>"`.
- 백그라운드 에디터는 약 1fps로 스로틀돼 스크린샷이 안 찍힌다: `-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False`.
- 촬영 에디터를 강제 종료하면 다음 실행에서 "패키지 복구" 창이 떠서 멈춘다. `Saved/Autosaves/PackageRestoreData.json`을 지운다.
- PostProcessVolume은 Brush의 하위 클래스라, "Brush는 남기고 지우기"로 레벨을 비우면 빌드할 때마다 색보정 볼륨이 쌓인다.
- 재질 변경은 대상 컴포넌트/에셋 API를 구분한다. 컴포넌트는 `set_material(index, mi)`. 이번 SkeletalMesh 에셋은 `SkeletalMaterial` 배열을 만들어 `set_editor_property('materials', ...)`로 지정·저장했다. 직접 슬롯 구조체 필드만 바꿨다면 실제 저장 결과를 확인한다.
- SceneCapture는 Lumen GI·노출 이력이 없어 새까맣거나 한 박자 늦다. 실제 뷰포트 스크린샷을 쓴다.
- Git Bash에서 `-Arg=/Game/...` 인자는 윈도우 경로로 바뀐다. `MSYS2_ARG_CONV_EXCL="-NyabloTrail="`처럼 막는다.
