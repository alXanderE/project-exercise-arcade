//
//  HealthKitManager.swift
//  ExerciseArcadeHealth
//
//  Created by Michael Palmer on 4/25/26.
//

import Foundation
import HealthKit

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

        guard let stepType = HKObjectType.quantityType(forIdentifier: .stepCount) else {
            throw HealthKitError.stepTypeUnavailable
        }

        let readTypes: Set<HKObjectType> = [stepType]

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
}
