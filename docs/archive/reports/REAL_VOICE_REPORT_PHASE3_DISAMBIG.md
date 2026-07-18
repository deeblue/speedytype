# Real Voice Report

Generated after user-provided recordings.

| # | 原始腳本 | Whisper | 修飾後 | 預期專有名詞 | 缺失專有名詞 | 專有名詞 | 自我修正 | 贅字 |
|---|---|---|---|---|---|---|---|---|
| 1 | 呃，請 TPE 團隊今天同步 BIOS 狀態。 | PD 團隊今天同步 BIOS 狀態 | PD 團隊今天同步 BIOS 狀態。 | BIOS, TPE 團隊 | TPE 團隊 | ❌ | ✅ | ✅ |
| 2 | 那個，QA 明天早上回報 NPI 測試結果。 | QA 明天早上回報 NPI 測試結果 | QA 明天早上回報 NPI 測試結果。 | NPI, QA | - | ✅ | ✅ | ✅ |
| 3 | 請 BJ 團隊確認 USB 相容性。 | 請 BJ 團隊確認 USB 相容性 | 請 BJ 團隊確認 USB 相容性。 | BJ 團隊, USB | - | ✅ | ✅ | ✅ |
| 4 | 我們原本下週二要開 Firmware review，啊不對，應該改到下週四下午。 | 下週二要開Firmware Review,啊不對,應該改到下週四下午 | 下週四下午要開 Firmware Review。 | Firmware | - | ✅ | ✅ | ✅ |
| 5 | 這版 API 文件先給 TPE 團隊，啊不對，先給 BJ 團隊確認術語。 | 文件先給 TPE 團隊 不對,先給 BJ 團隊確認術語 | 文件先給 BJ 團隊確認術語。 | API, TPE 團隊, BJ 團隊 | API, TPE 團隊 | ❌ | ✅ | ✅ |
| 6 | 就是說，Firmware 更新後，BIOS 和 Thunderbolt 的測試紀錄要一起附上。 | 更新後,BIOS和Thunderbolt的測試紀錄要一起附上 | 更新後，請一併附上 BIOS 與 Thunderbolt 的測試紀錄。 | BIOS, Firmware, Thunderbolt | Firmware | ❌ | ✅ | ✅ |
| 7 | 然後 TPE 團隊、BJ 團隊和 QA 需要在 NPI 會議前完成風險整理。 | TPE 團隊, BJ 團隊和 QA 需要在 NPI 會議前完成風險整理 | TPE 團隊、BJ 團隊和 QA 需要在 NPI 會議前完成風險整理。 | NPI, QA, TPE 團隊, BJ 團隊 | - | ✅ | ✅ | ✅ |
| 8 | 今天要完成三件事，第一，更新 Firmware release note，第二，整理 USB 和 Thunderbolt 的相容性問題，第三，把 API 測試結果寄給 QA 和 TPE 團隊。 | 完成三件事 第一,更新Firmware Release Note 第二,整理USB和Thunderbolt的相容性問題 第三,把API測試結果寄給QA和TPE團隊 | 完成以下三項任務：

1. 更新 Firmware Release Note。
2. 整理 USB 與 Thunderbolt 的相容性問題。
3. 將 API 測試結果寄送給 QA 與 TPE 團隊。 | Firmware, QA, API, TPE 團隊, USB, Thunderbolt | - | ✅ | ✅ | ✅ |
| 9 | 我們先請 BJ 團隊測 BIOS，啊不對，先請 TPE 團隊測 BIOS，再由 QA 比對 NPI checklist，最後把異常項目整理給 Firmware owner。 | 先請 TPE 團隊測 BIOS,再由 QA 比對 NPI Checklist,最後把異常項目整理給 Firmware Owner | 1. 請 TPE 團隊測試 BIOS。
2. 由 QA 比對 NPI Checklist。
3. 將異常項目整理並提供給 Firmware Owner。 | BIOS, Firmware, NPI, QA, TPE 團隊, BJ 團隊 | BJ 團隊 | ❌ | ✅ | ✅ |
| 10 | 那個如果今天辦公室比較吵，還是請先用 SpeedyType 記錄問題，包含 BIOS、Firmware、API 和 Thunderbolt 四個關鍵字，然後再人工確認一次。 | 如果今天辦公室比較吵 還是請先用SpeedyType記錄問題 包含BIOS, Firmware, NPI和Thunderbolt四個關鍵字 然後再人工確認一次 | 若辦公室環境較吵雜，請先使用 SpeedyType 記錄問題，並確保包含以下四個關鍵字：

* BIOS
* Firmware
* NPI
* Thunderbolt

記錄完成後，再進行人工確認。 | BIOS, Firmware, API, Thunderbolt | API | ❌ | ✅ | ✅ |

## Summary

- 專有名詞辨識正確率：50.0%
- 自我修正處理正確率：100.0%
- 贅字清除正確率：100.0%

## Per-Term Accuracy

| 詞彙 | 正確次數 | 出現次數 | 正確率 |
|---|---:|---:|---:|
| BIOS | 4 | 4 | 100.0% |
| Firmware | 4 | 5 | 80.0% |
| NPI | 3 | 3 | 100.0% |
| QA | 4 | 4 | 100.0% |
| API | 1 | 3 | 33.3% |
| TPE 團隊 | 3 | 5 | 60.0% |
| BJ 團隊 | 3 | 4 | 75.0% |
| USB | 2 | 2 | 100.0% |
| Thunderbolt | 3 | 3 | 100.0% |
