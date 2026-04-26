//
//  ArcadeAPIClient.swift
//  ExerciseArcadeHealth
//
//  Created by Michael Palmer on 4/25/26.
//

import Foundation

struct LoginPayload: Codable {
    let identifier: String
    let email: String
    let password: String
}

struct FitnessSyncPayload: Codable {
    let loggedOn: String
    let steps: Int
    let workoutMinutes: Int
    let activeCalories: Int
    let distanceMiles: Double
    let source: String
    let notes: String
}

struct SyncStepsResponse: Codable {
    let message: String
    let pointsDelta: Int
}


final class ArcadeAPIClient {
    private let baseURL = URL(
        string: "https://project-exercise-arcade-git-main-alxanderes-projects.vercel.app"
    )!

    private let session = URLSession.shared

    func login(email: String, password: String) async throws {
        let url = URL(string: "/api/auth/login", relativeTo: baseURL)!.absoluteURL

        let cleanedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanedPassword = password.trimmingCharacters(in: .whitespacesAndNewlines)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(
            LoginPayload(
                identifier: cleanedEmail,
                email: cleanedEmail,
                password: cleanedPassword
            )
        )

        try await send(request)
    }

    func syncFitness(
        steps: Int,
        workoutMinutes: Int,
        activeCalories: Int,
        distanceMiles: Double
    ) async throws -> SyncStepsResponse {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"

        let payload = FitnessSyncPayload(
            loggedOn: formatter.string(from: Date()),
            steps: steps,
            workoutMinutes: workoutMinutes,
            activeCalories: activeCalories,
            distanceMiles: distanceMiles,
            source: "apple_health",
            notes: "Synced from Apple Health"
        )

        let url = URL(string: "/api/fitness/steps", relativeTo: baseURL)!.absoluteURL

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(payload)

        return try await send(request, as: SyncStepsResponse.self)
    }

    private func send(_ request: URLRequest) async throws {
        let (_, response) = try await validatedData(for: request)

        guard response is HTTPURLResponse else {
            throw NSError(
                domain: "ArcadeAPI",
                code: 0,
                userInfo: [NSLocalizedDescriptionKey: "Invalid server response."]
            )
        }
    }

    private func send<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let (data, _) = try await validatedData(for: request)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func validatedData(for request: URLRequest) async throws -> (Data, URLResponse) {
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw NSError(
                domain: "ArcadeAPI",
                code: 0,
                userInfo: [NSLocalizedDescriptionKey: "Invalid server response."]
            )
        }

        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "No response body"
            throw NSError(
                domain: "ArcadeAPI",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: body]
            )
        }

        return (data, response)
    }

}
