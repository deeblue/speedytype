# Real Voice Report

Generated after user-provided recordings.

| # | 原始腳本 | Whisper | 修飾後 | 預期專有名詞 | 缺失專有名詞 | 專有名詞 | 自我修正 | 贅字 |
|---|---|---|---|---|---|---|---|---|
| 1 | 呃，請 QA 今天補上 BIOS 測試結果。 | 請 QA 今天補上 BIOS 測試結果 | 請 QA 今天補上 BIOS 測試結果。 | BIOS, QA | - | ✅ | ✅ | ✅ |
| 2 | 那個，USB 相容性先給 BJ 團隊確認。 | USB 相信先給 BJ 團隊確認 | USB 相關事宜請先交由 BJ 團隊確認。 | BJ 團隊, USB | - | ✅ | ✅ | ✅ |
| 3 | 請把 API 規格同步給 TPE 團隊。 | 請把 API 規格同步給 TPE 團隊 | 請將 API 規格同步給 TPE 團隊。 | API, TPE 團隊 | - | ✅ | ✅ | ✅ |
| 4 | Firmware 版本更新後，Thunderbolt 的回歸測試要再跑一次。 | Firmware版本更新後,Thunderbolt回歸測試要再跑一次。 | Firmware 版本更新後，Thunderbolt 回歸測試需重新執行。 | Firmware, Thunderbolt | - | ✅ | ✅ | ✅ |
| 5 | 我們這週的 NPI 進度先讓 PD 團隊看過，再交給 QA 整理。 | 我們這時候的NPI進度先讓PD團隊看過,再交給QA整理 | 我們目前的 NPI 進度會先由 PD 團隊審閱，再交由 QA 團隊進行整理。 | NPI, QA | - | ✅ | ✅ | ✅ |
| 6 | 請 BJ 團隊先看 BIOS 設定，再把異常回報給 Firmware owner。 | 請 BJ 團隊先看 BIOS 設定,再把異常回報給 Firmware Owner | 請 BJ 團隊先確認 BIOS 設定，並將異常回報給 Firmware Owner。 | BIOS, Firmware, BJ 團隊 | - | ✅ | ✅ | ✅ |
| 7 | 就是說，API 測試失敗的案例，先不要關單，等 TPE 團隊確認根因。 | 就是說,AVM測試失敗的案例先不要關單,等 TPE 團隊確認更新 | AVM 測試失敗的案例請暫時不要關單，待 TPE 團隊確認更新後再處理。 | API, TPE 團隊 | API | ❌ | ✅ | ✅ |
| 8 | 然後 USB 和 Thunderbolt 的問題單，要在下次 NPI 會議前整理完。 | 然後 USB 和 Thunderbolt 的問題單 要在下一次 NPI 會議前整理完 | USB 和 Thunderbolt 的問題單需在下一次 NPI 會議前整理完畢。 | NPI, USB, Thunderbolt | - | ✅ | ✅ | ✅ |
| 9 | 我本來想請 BJ 團隊處理，啊不對，這題應該先給 TPE 團隊確認。 | 我本來想請 BJ 團隊處理update,這題應該先給 TPE 團隊確認。 | 這題應該先給 TPE 團隊確認。 | TPE 團隊, BJ 團隊 | BJ 團隊 | ✅ | ✅ | ✅ |
| 10 | 明天先寄 API 文件，不對，應該先寄 NPI checklist 給 QA。 | 明天先寄 API 文件,不對,應該先寄 NPI Checklist 給 QA | 明天請先寄送 NPI Checklist 給 QA。 | NPI, QA, API | API | ✅ | ✅ | ✅ |
| 11 | 今天要完成三件事，第一，更新 BIOS 和 Firmware 的版本說明，第二，把 API 測試結果寄給 QA 和 BJ 團隊，第三，確認 USB 跟 Thunderbolt 的相容性風險。 | 今天完成三件事 第一,更新BIOS和Firmware的版本說明 第二,把API測試結果寄給QA和BJ團隊 第三,確認USB跟Thunderbolt的相容性風險 | 今日完成事項：

1. 更新 BIOS 和 Firmware 的版本說明。
2. 將 API 測試結果寄給 QA 和 BJ 團隊。
3. 確認 USB 與 Thunderbolt 的相容性風險。 | BIOS, Firmware, QA, API, BJ 團隊, USB, Thunderbolt | - | ✅ | ✅ | ✅ |
| 12 | 這週專案同步時，TPE 團隊要先講 BIOS 狀態，BJ 團隊補充 Firmware 風險，QA 再說明 NPI 測試進度。 | 這週初案同步時, TPE 團隊要先講 BIOS 狀態, BJ 團隊補充 Firmware 風險, QA 再說明 NPI 測試進度 | 本週初案同步會議流程如下：

*   TPE 團隊：說明 BIOS 狀態。
*   BJ 團隊：補充 Firmware 風險。
*   QA：說明 NPI 測試進度。 | BIOS, Firmware, NPI, QA, TPE 團隊, BJ 團隊 | - | ✅ | ✅ | ✅ |
| 13 | 如果今天會議時間不夠，就先講 API 變更、Firmware 版本差異，還有下週 NPI 需要追的項目。 | 如果今天會議時間不夠,就先講 API 變更, Firmware 版本差異,還有下週 NPI 需要追的項目。 | 若今日會議時間不足，請優先討論以下事項：

* API 變更
* Firmware 版本差異
* 下週 NPI 需追蹤項目 | Firmware, NPI, API | - | ✅ | ✅ | ✅ |
| 14 | 我們原本打算先測 USB，再測 Thunderbolt，啊不對，應該先把 BIOS 更新完再一起驗證。 | 我們有沒有打算先測USB,再測Thunderbolt? 啊,不對,應該先把BIOS更新完再一起驗證 | 我們應該先將 BIOS 更新完畢，再一併驗證 USB 與 Thunderbolt。 | BIOS, USB, Thunderbolt | - | ✅ | ✅ | ✅ |
| 15 | 請你記下三個重點，第一個是 API 規格不要再改，第二個是 QA 今天要補 BIOS log，第三個是 TPE 團隊和 BJ 團隊都要回報 Firmware 狀態。 | 請你記下三個重點,第一個是API規格不要再改 第二個是QA今天要回BIOS LOG 第三個是TPE團隊和BJ團隊都要回報Firmware狀態 | 1. API 規格請勿再進行更動。
2. QA 團隊需於今日回報 BIOS LOG。
3. TPE 團隊與 BJ 團隊皆須回報 Firmware 狀態。 | BIOS, Firmware, QA, API, TPE 團隊, BJ 團隊 | - | ✅ | ✅ | ✅ |
| 16 | 如果辦公室很吵，還是請先用 SpeedyType 記錄問題，內容至少要包含 BIOS、Firmware、NPI、API、USB 和 Thunderbolt，之後再人工確認一次。 | 如果辦公室很吵,還是請先用 SpeedyType 記錄問題,內容至少還要包含 BIOS, Firmware, NPI, API, USB 和 Thunderbolt,之後再人工確認一次。 | 若辦公室環境吵雜，請先使用 SpeedyType 記錄問題，內容需包含以下項目，並於事後進行人工確認：

*   BIOS
*   Firmware
*   NPI
*   API
*   USB
*   Thunderbolt | BIOS, Firmware, NPI, API, USB, Thunderbolt | - | ✅ | ✅ | ✅ |

## Summary

- 專有名詞辨識正確率：93.8%
- 自我修正處理正確率：100.0%
- 贅字清除正確率：100.0%

## Per-Term Accuracy

| 詞彙 | 正確次數 | 出現次數 | 正確率 |
|---|---:|---:|---:|
| BIOS | 7 | 7 | 100.0% |
| Firmware | 7 | 7 | 100.0% |
| NPI | 6 | 6 | 100.0% |
| QA | 6 | 6 | 100.0% |
| API | 5 | 7 | 71.4% |
| TPE 團隊 | 5 | 5 | 100.0% |
| BJ 團隊 | 5 | 6 | 83.3% |
| USB | 5 | 5 | 100.0% |
| Thunderbolt | 5 | 5 | 100.0% |
