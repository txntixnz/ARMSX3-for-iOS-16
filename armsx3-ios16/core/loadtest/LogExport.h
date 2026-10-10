// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <string>
#include <string_view>
#include <vector>

// The on-disk log is append-only across launches. Export one complete launch,
// including the previous launch when the app reopened after an unfinished run.
inline std::string armsx3_startup_log_session(std::string_view log, bool previous)
{
    std::vector<size_t> starts;
    size_t line = 0;
    while (line < log.size()) {
        const size_t newline = log.find('\n', line);
        const size_t end = newline == std::string_view::npos ? log.size() : newline;
        if (log.substr(line, end - line).ends_with(" P2 main entered")) starts.push_back(line);
        if (newline == std::string_view::npos) break;
        line = newline + 1;
    }
    if (starts.empty()) return std::string(log);
    size_t index = previous && starts.size() > 1 ? starts.size() - 2 : starts.size() - 1;
    if (previous && starts.size() > 1) {
        // Reopening repeatedly before testing must keep the crashed run
        // available, skipping launches that only displayed the diagnostics UI.
        for (size_t candidate = starts.size() - 1; candidate-- > 0;) {
            const auto session = log.substr(starts[candidate], starts[candidate + 1] - starts[candidate]);
            if (session.find(" AUTO BEFORE ") != std::string_view::npos) { index = candidate; break; }
        }
    }
    const size_t end = index + 1 < starts.size() ? starts[index + 1] : log.size();
    return std::string(log.substr(starts[index], end - starts[index]));
}

inline std::string armsx3_startup_log_tail(std::string_view log, size_t lines)
{
    if (!lines || log.empty()) return {};
    size_t end = log.size();
    if (log.back() == '\n') --end;
    for (size_t count = 0; count < lines; ++count) {
        if (!end) return std::string(log);
        const size_t newline = log.rfind('\n', end - 1);
        if (newline == std::string_view::npos) return std::string(log);
        if (count + 1 == lines) return std::string(log.substr(newline + 1));
        end = newline;
    }
    return std::string(log);
}
