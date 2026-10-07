# 준비

## 도구

| 도구 | 이 PC | 용도 | 확인 |
| --- | --- | --- | --- |
| Blender 5.2 | `D:/blander/blender.exe` | 모든 3D 처리(배경 모드) | `blender -b --version` |
| Tripo CLI 0.5.1 | `npm i tripo-cli` → `node_modules/.bin/tripo.cmd` | 생성·면 줄이기·부위 분리·리깅·프리셋 동작 | `tripo whoami`, `tripo balance` |
| codex CLI | `codex` (ChatGPT 로그인) | 설정화 이미지 생성·편집 | `codex login status` |
| Python 3 + numpy, opencv-python, Pillow | 시스템 python | 텍스처 보정(`fix_textures.py` 등) | `python -c "import numpy, cv2, PIL"` |
| Unreal Engine 5.8 | `C:/Program Files/Epic Games/UE_5.8` | 게임 설치·검증. C++ 모듈이 있는 프로젝트 | |
| VS 2022 Build Tools (MSVC 14.44) | | Unreal C++ 빌드(천 설정·동작 섞기) | |
| Chrome + Adobe 로그인 | | Mixamo 동작 받기 | |

- 경로는 `$SKILL/config.env`에 있다. 다른 PC에서는 여기만 고친다. Python 도구는 경로를 모두 인자로 받는다.
- Tripo 인증: `tripo login`(브라우저 승인), 키는 `~/.tripo/config.json`에 저장된다.
- codex 이미지 생성 방법은 `codex-image` 스킬을 따른다. 이 스킬의 `scripts/run_codex.sh`는 결과가 작업 폴더로 복사되지 않았을 때 codex 세션 폴더(`generated_images/<session>`)에서 가져온다.

## 창 없이 실행

Claude Code·Codex의 셸에는 콘솔이 없어서, 콘솔 프로그램을 직접 실행하면 매번 새 창이 떠서 사용자 화면의 포커스를 빼앗는다.

```bash
pythonw $SKILL/scripts/nowin.py "$BLENDER" -b --factory-startup -P $SKILL/scripts/<tool>.py -- <args>
pythonw $SKILL/scripts/nowin.py "$UE_ROOT/Engine/Binaries/Win64/UnrealEditor.exe" <uproject> -game -RenderOffScreen ...
pythonw $SKILL/scripts/nowin.py codex exec ... < /dev/null
```

- `nowin.py`는 자식 프로세스를 `CREATE_NO_WINDOW` + `SW_HIDE`로 띄우고 출력을 그대로 넘긴다. 자식이 다시 띄우는 프로세스(예: Blender 안에서 부르는 `fix_textures.py`)도 창이 없다.
- `codex exec`는 표준 입력을 기다리며 멈출 수 있다. 반드시 `< /dev/null`을 붙인다(한 번 1시간 멈췄다).
- 창이 뜨는지 의심되면 `scripts/winwatch.py`(WinEvent 훅)로 새로 뜬 창과 부모 프로세스를 기록한다. 냐블로에서 사용자 화면에 뜨던 콘솔은 Codex 앱 데몬의 `git.exe`였다.

## Tripo 크레딧과 장부

- 크레딧은 사용자 승인 범위 안에서 쓴다. 단계마다 쓴 양과 잔액(`tripo balance`)을 보고한다.
- 작업 제출은 `scripts/tripo_step.sh <출력 폴더> <에셋 이름> <tripo 명령...>`로 한다. `--out --json --no-open --yes --timeout 3600`을 붙이고, 태스크 ID·크레딧·상태를 출력하고, 장부(`$LEDGER`, 기본 `./tripo_ledger.jsonl`)에 한 줄을 남긴다. 이 스크립트는 작업 제출용(generate·mesh·anim)이다. `task get`에는 `--timeout` 옵션이 없어서 쓸 수 없다.
- 결과 복구: `tripo task get <id> --download -o <dir>`.
- 실패한 작업은 대부분 자동 환불된다. 같은 실패를 반복 제출하지 않는다(pitfalls.md).

## 대략적인 비용 (데스나이트 기준)

| 항목 | 크레딧 |
| --- | --- |
| 통짜 몸 multiview-to-model (detailed) | 60 |
| 부위 4종(머리·팔·몸통·하체) × 60 | 240 |
| 면 줄이기 × 5~6 | 50~60 |
| 리깅 25 + 프리셋 동작 2개 20 | 45 |
| 무기 생성 60 + 면 줄이기 10 | 70 |
| 합계 | 약 465 |

설정화에서 4방향 이미지를 codex로 그리면 `image-to-multiview`(10)는 필요 없다.
