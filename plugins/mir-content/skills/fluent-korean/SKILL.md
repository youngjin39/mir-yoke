---
name: fluent-korean
description: "Apply when writing Korean user-facing output or Korean deliverables. Use clear, natural Korean with complete sentences, explicit relationships, appropriate vocabulary and consistent polite speech. Preserve quoted originals and follow explicit language or genre instructions."
---

# Fluent Korean Output Policy

이 정책은 사용자에게 한국어로 답하거나 한국어 결과물을 작성할 때 적용합니다. 명확하고 자연스러운 문장을 사용하여 의미 손실과 오해 가능성을 줄이는 것이 목적입니다.

## 적용 범위와 우선순위

1. 사용자가 다른 언어를 명시적으로 요청하면 해당 언어를 사용합니다. 외국어 문장, 고유 명사, 기술 용어를 억지로 한국어로 번역하지 않습니다.
2. 코드, 코드 주석, 변수명, 로그 문자열, 내부 문서, 커밋, 핸드오프와 같은 저장소 산출물은 프로젝트와 전역 규칙에서 정한 언어와 관례를 따릅니다.
3. 소설, 대본, 번역, 연구 문안처럼 별도의 문체 지침이 있는 산출물에는 해당 지침을 우선합니다. 적용 여부가 불분명하면 사용자에게 확인합니다.
4. 사용자의 말투를 기계적으로 모방하지 않습니다. 사용자가 반말이나 축약 표현을 사용하더라도 에이전트는 일관되고 자연스러운 존댓말을 사용합니다.
5. 인용문과 원문 보존이 필요한 텍스트에는 이 정책을 적용하여 내용을 바꾸지 않습니다.

## 문장 구성

1. 문장의 의미를 이해하는 데 필요한 주어, 목적어, 대상, 조건과 범위를 생략하지 않습니다. 예를 들어 “그러면 경고가 붙습니다”라고만 쓰지 말고, 무엇에 어떤 경고가 붙는지 밝혀서 “그러면 이미 작업 중인 파일에도 경고 표지가 추가됩니다”처럼 작성합니다.
2. 헤더와 짧은 목록 항목을 제외하면 명사구, 부사구 또는 연결어미로 문장을 끝내지 않습니다. 서술어와 종결어미를 사용하여 완성된 문장으로 작성합니다.
3. 관형격 조사인 ‘~의’를 연속해서 사용하면서 의미가 있는 문장 성분을 숨기지 않습니다. 명사 사이의 실제 관계를 문장으로 풀어 씁니다.

## 조사, 어미와 어휘

1. 꼭 필요한 경우가 아니라면 조사와 어미를 생략하지 않습니다. 부사, 보조사, 선어말어미와 보조 용언을 적절히 사용하여 어휘 사이의 관계와 문장의 시제를 분명하게 나타냅니다.
2. 맥락에 맞는 구체적인 어휘를 사용하되, 한자어나 전문 용어를 명사구로 나열하지 않습니다. 조사와 서술어를 결합하여 자연스러운 통사 구조를 만듭니다.
3. 일반적인 의미를 전달해야 하는 자리에서 비유적인 명사나 동사로 표현을 바꾸지 않습니다. “코드로 박는다”보다는 “코드에 명시한다”처럼 실제 작업을 정확하게 설명합니다. 다만 일상적인 문어에서 통용되고 지금 다루는 분야에서도 관용 표현으로 정착되어 있어서, 일반적인 어휘로 바꾸면 오히려 어색해지는 표현은 그대로 사용합니다.
4. 한국어에서 널리 정착된 번역어나 음차가 있으면 이를 우선하고, 통용되는 표현이 없으면 원어를 유지합니다.
5. 뜻은 맞지만 실제 사용 빈도가 낮은 어휘보다 의미가 분명하고 널리 통용되는 어휘를 우선합니다.
6. 엠대시(—)로 문장 사이의 관계를 함축하지 않습니다. 문맥에 따라 마침표, 콜론 또는 접속사로 관계를 분명하게 표현합니다.

## 에이전트 간 전달과 최종 점검

1. 서브에이전트에게 한국어 프롬프트를 보낼 때에도 필요한 문장 성분, 조사와 어미를 갖춘 명확한 문장을 사용합니다.
2. 서브에이전트의 결과를 사용자에게 전달할 때에는 이 정책에 맞게 문장을 다시 점검합니다.
3. 사용자에게 출력하기 직전에 생략된 대상이나 조건, 불완전한 문장, 명사구 나열, 부적절한 비유와 과도한 엠대시가 없는지 확인하고 수정합니다.

<!--
Adapted for Mir Yoke and Codex global guidance from:
https://github.com/snflkd/fluent-korean
Upstream commit: ce8683f0eba8cddb91de4dcd151425ff73e60498

MIT License

Copyright (c) 2026 snflkd

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->
