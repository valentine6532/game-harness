# 웹 페이지 틀

- `privacy.html`, `privacy-en.html`, `privacy-ja.html`: 개인정보 처리방침. 채우는 법은 `privacy.html` 맨 위 주석.
- `support.html`, `support-en.html`, `support-ja.html`: 스토어의 지원 URL에 쓰는 문의 페이지.
- `firebase.json`: 저장소 루트에 복사. `public`은 페이지를 둔 폴더 이름(기본 `store-site`).
- `.firebaserc.example`: 프로젝트 ID를 넣어 저장소 루트에 `.firebaserc`로 저장.

페이지 파일은 저장소의 `store-site/` 같은 폴더에 복사해 쓴다. 색과 글꼴은 앱에 맞게 고쳐도 된다.
지원하지 않는 언어의 파일은 지우고, 각 페이지 위쪽의 언어 링크도 함께 정리한다.
게시 후 `.firebase/` 캐시 폴더가 생기므로 `.gitignore`에 추가한다.
