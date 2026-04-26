//
//  HealthKitManager.swift
//  ExerciseArcadeHealth
//
//  Created by Michael Palmer on 4/25/26.
//

import Foundation
import HealthKit

struct WorkoutSummary {
    let workoutCount: Int
    let workoutMinutes: Int
    let activeCalories: Int
    let distanceMiles: Double
}


enum HealthKitError: LocalizedError {
    case healthDataUnavailable
    case stepTypeUnavailable

    var errorDescription: String? {
        switch self {
        case .healthDataUnavailable:
            return "Health data is not available on this device."
        case .stepTypeUnavailable:
            return "Step count is not available."
        }
    }
}

final class HealthKitManager {
    private let healthStore = HKHealthStore()

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw HealthKitError.healthDataUnavailable
        }

        guard let stepType = HKObjectType.quantityType(forIdentifier: .stepCount),
              let activeEnergyType = HKObjectType.quantityType(forIdentifier: .activeEnergyBurned),
              let distanceType = HKObjectType.quantityType(forIdentifier: .distanceWalkingRunning) else {
            throw HealthKitError.stepTypeUnavailable
        }

        let workoutType = HKObjectType.workoutType()

        let readTypes: Set<HKObjectType> = [
            stepType,
            activeEnergyType,
            distanceType,
            workoutType
        ]

        try await healthStore.requestAuthorization(toShare: [], read: readTypes)
    }

    func fetchTodaySteps() async throws -> Int {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw HealthKitError.healthDataUnavailable
        }

        guard let stepType = HKObjectType.quantityType(forIdentifier: .stepCount) else {
            throw HealthKitError.stepTypeUnavailable
        }

        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: Date())

        let predicate = HKQuery.predicateForSamples(
            withStart: startOfDay,
            end: Date(),
            options: .strictStartDate
        )

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKStatisticsQuery(
                quantityType: stepType,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, result, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                let steps = result?
                    .sumQuantity()?
                    .doubleValue(for: HKUnit.count()) ?? 0

                continuation.resume(returning: Int(steps))
            }

            healthStore.execute(query)
        }
    }

    func fetchTodayWorkoutSummary() async throws -> WorkoutSummary {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw HealthKitError.healthDataUnavailable
        }

        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: Date())

        let predicate = HKQuery.predicateForSamples(
            withStart: startOfDay,
            end: Date(),
            options: .strictStartDate
        )

        let workouts = try await fetchWorkouts(predicate: predicate)

        let activeCalories = try await fetchQuantityTotal(
            identifier: .activeEnergyBurned,
            predicate: predicate,
            unit: .kilocalorie()
        )

        let distanceMiles = try await fetchQuantityTotal(
            identifier: .distanceWalkingRunning,
            predicate: predicate,
            unit: .mile()
        )

        let totalSeconds = workouts.reduce(0) { total, workout in
            total + workout.duration
        }

        return WorkoutSummary(
            workoutCount: workouts.count,
            workoutMinutes: Int(totalSeconds / 60),
            activeCalories: Int(activeCalories),
            distanceMiles: distanceMiles
        )
    }

    private func fetchWorkouts(predicate: NSPredicate) async throws -> [HKWorkout] {
        try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: HKObjectType.workoutType(),
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: nil
            ) { _, samples, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                let workouts = samples as? [HKWorkout] ?? []
                continuation.resume(returning: workouts)
            }

            healthStore.execute(query)
        }
    }

    private func fetchQuantityTotal(
        identifier: HKQuantityTypeIdentifier,
        predicate: NSPredicate,
        unit: HKUnit
    ) async throws -> Double {
        guard let quantityType = HKObjectType.quantityType(forIdentifier: identifier) else {
            return 0
        }

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKStatisticsQuery(
                quantityType: quantityType,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, result, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }

                let value = result?.sumQuantity()?.doubleValue(for: unit) ?? 0
                continuation.resume(returning: value)
            }

            healthStore.execute(query)
        }
    }

}
