//
//  ContentView.swift
//  ExerciseArcadeHealth
//
//  Created by Michael Palmer on 4/25/26.
//

import SwiftUI

struct ContentView: View {
    @State private var steps = 0
    @State private var statusMessage = "Connect Apple Health to read steps."
    @State private var email = ""
    @State private var password = ""
    @State private var workoutMinutes = 0
    @State private var workoutCount = 0
    @State private var activeCalories = 0
    @State private var distanceMiles = 0.0


    private let healthKitManager = HealthKitManager()
    private let apiClient = ArcadeAPIClient()

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "figure.walk.circle.fill")
                    .imageScale(.large)
                    .font(.system(size: 56))
                    .foregroundStyle(.tint)

                Text("Exercise Arcade")
                    .font(.largeTitle)
                    .bold()

                Text("\(steps)")
                    .font(.system(size: 56, weight: .bold))

                Text("steps today")
                    .foregroundStyle(.secondary)

                Text("\(workoutMinutes) workout minutes")
                    .foregroundStyle(.secondary)

                Text("\(activeCalories) active calories")
                    .foregroundStyle(.secondary)

                Text(String(format: "%.2f miles", distanceMiles))
                    .foregroundStyle(.secondary)

                Button("Connect Apple Health") {
                    Task {
                        do {
                            try await healthKitManager.requestAuthorization()
                            statusMessage = "Apple Health connected."
                        } catch {
                            statusMessage = error.localizedDescription
                        }
                    }
                }
                .buttonStyle(.borderedProminent)

                Button("Fetch Today’s Steps") {
                    Task {
                        do {
                            steps = try await healthKitManager.fetchTodaySteps()
                            statusMessage = "Steps updated."
                        } catch {
                            statusMessage = error.localizedDescription
                        }
                    }
                }
                .buttonStyle(.bordered)

                Button("Fetch Today’s Workouts") {
                    Task {
                        do {
                            let summary = try await healthKitManager.fetchTodayWorkoutSummary()

                            workoutCount = summary.workoutCount
                            workoutMinutes = summary.workoutMinutes
                            activeCalories = summary.activeCalories
                            distanceMiles = summary.distanceMiles

                            statusMessage = "Workout data updated."
                        } catch {
                            statusMessage = error.localizedDescription
                        }
                    }
                }
                .buttonStyle(.bordered)

                VStack(spacing: 12) {
                    TextField("Exercise Arcade email", text: $email)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.emailAddress)
                        .textFieldStyle(.roundedBorder)

                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)

                    Button("Sync Fitness to Arcade") {
                        Task {
                            do {
                                let cleanedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
                                let cleanedPassword = password.trimmingCharacters(in: .whitespacesAndNewlines)

                                statusMessage = "Trying login for \(cleanedEmail), password length \(cleanedPassword.count)"

                                try await apiClient.login(
                                    email: cleanedEmail,
                                    password: cleanedPassword
                                )


                                let result = try await apiClient.syncFitness(
                                    steps: steps,
                                    workoutMinutes: workoutMinutes,
                                    activeCalories: activeCalories,
                                    distanceMiles: distanceMiles
                                )

                                statusMessage = "Fitness synced. +\(result.pointsDelta) points awarded."

                            } catch {
                                statusMessage = error.localizedDescription
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        email.isEmpty ||
                        password.isEmpty ||
                        (steps == 0 && workoutMinutes == 0 && activeCalories == 0)
                    )
                }
                .padding(.top, 12)

                Text(statusMessage)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding()
        }
    }
}

#Preview {
    ContentView()
}
