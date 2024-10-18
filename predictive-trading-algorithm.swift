import TabularData
import CoreML
import Accelerate
import Combine

// MARK: - Exponential Moving Average (EMA) Calculation
func exponentialMovingAverage(prices: [Double], smoothing: Double, window: Int) -> [Double] {
    var ema = [Double](repeating: 0.0, count: prices.count)
    let multiplier = smoothing / (1 + Double(window))
    
    ema[0] = prices[0]  // Initialize with the first price
    for i in 1..<prices.count {
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
    }
    return ema
}

// MARK: - Kalman Filter for Signal Smoothing
func kalmanFilter(signal: [Double]) -> [Double] {
    var filteredSignal = [Double](repeating: 0.0, count: signal.count)
    var errorCovariance = 1.0
    var processNoise = 0.1
    var estimatedVariance = 1.0
    
    for i in 1..<signal.count {
        let kalmanGain = errorCovariance / (errorCovariance + processNoise)
        filteredSignal[i] = filteredSignal[i - 1] + kalmanGain * (signal[i] - filteredSignal[i - 1])
        errorCovariance = (1 - kalmanGain) * estimatedVariance
    }
    return filteredSignal
}

// MARK: - LSTM Model Prediction Class
class LSTMPricePredictor {
    private let model: LSTMPricePredictorModel
    
    init() {
        model = try! LSTMPricePredictorModel()
    }
    
    func predictNextPrice(input: [Double]) -> Double? {
        let mlArray = try? MLMultiArray(shape: [3], dataType: .double)
        for (index, value) in input.enumerated() {
            mlArray?[index] = NSNumber(value: value)
        }
        let input = LSTMPricePredictorModelInput(input: mlArray!)
        let prediction = try? model.prediction(input: input)
        return prediction?.output.doubleValue
    }
}

// MARK: - Trading Signal Generator with LSTM Prediction and EMA Crossover
func tradingSignalWithLSTM(
    prices: [Double], predictor: LSTMPricePredictor, shortWindow: Int = 40, longWindow: Int = 100
) async -> [Int] {
    async let shortEMA = exponentialMovingAverage(prices: prices, smoothing: 2, window: shortWindow)
    async let longEMA = exponentialMovingAverage(prices: prices, smoothing: 2, window: longWindow)
    
    let shortMA = await shortEMA
    let longMA = await longEMA
    
    // Generate signals using LSTM predictions and EMA crossover
    var signals = [Int](repeating: 0, count: prices.count)
    for i in (3..<prices.count) {
        let input = Array(prices[(i - 3)...(i - 1)])
        if let predictedPrice = predictor.predictNextPrice(input: input),
           predictedPrice > prices[i],
           shortMA[i] > longMA[i] {
            signals[i] = 1  // Predict upward trend and EMA crossover (Buy)
        } else {
            signals[i] = 0  // Predict downward trend or no EMA crossover (Sell/Hold)
        }
    }
    
    let positions = zip(signals.dropFirst(), signals.dropLast()).map { $0 - $1 }
    return kalmanFilter(signal: positions)
}

// MARK: - Combine Publisher for Real-Time Trading Signals
class PredictiveLSTMTradingSignalPublisher {
    private let subject = PassthroughSubject<[Int], Never>()
    var publisher: AnyPublisher<[Int], Never> { subject.eraseToAnyPublisher() }
    private let predictor = LSTMPricePredictor()
    
    func update(prices: [Double]) {
        Task {
            let signals = await tradingSignalWithLSTM(prices: prices, predictor: predictor)
            subject.send(signals)
        }
    }
}

// MARK: - Example Usage
let prices: [Double] = (0..<500).map { _ in Double.random(in: 0...100) }
let lstmSignalPublisher = PredictiveLSTMTradingSignalPublisher()

let cancellable = lstmSignalPublisher.publisher
    .sink { signals in
        print("Latest Predictive LSTM Signals: \(signals.suffix(5))")
    }

// Trigger prediction-based signal generation
lstmSignalPublisher.update(prices: prices)
