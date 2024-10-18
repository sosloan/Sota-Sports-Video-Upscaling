// MARK: - Combining Asynchronous Sequences

// chain: Concatenates two or more asynchronous sequences with the same element type.
let sequence1 = [1, 2, 3].async
let sequence2 = [4, 5, 6].async
let chainedSequence = chain(sequence1, sequence2)
for await value in chainedSequence {
    print(value) // Output: 1, 2, 3, 4, 5, 6
}

// combineLatest: Combines two or more asynchronous sequences into an asynchronous sequence 
// producing a tuple of elements from those base asynchronous sequences that updates when 
// any of the base sequences produce a value.
let combineLatestSequence = combineLatest(sequence1, sequence2)
for await tuple in combineLatestSequence {
    print(tuple) // Output: (1, 4), (2, 4), (3, 4), (3, 5), (3, 6)
}

// merge: Merges two or more asynchronous sequences into a single asynchronous sequence 
// producing the elements of all of the underlying asynchronous sequences.
let mergedSequence = merge(sequence1, sequence2)
for await value in mergedSequence {
    print(value) // Output: 1, 4, 2, 5, 3, 6 (order may vary)
}

// zip: Creates an asynchronous sequence of pairs built out of underlying asynchronous sequences.
let zippedSequence = zip(sequence1, sequence2)
for await pair in zippedSequence {
    print(pair) // Output: (1, 4), (2, 5), (3, 6)
}

// joined: Concatenates elements of an asynchronous sequence of asynchronous sequences, 
// inserting the given separator between each element.
let nestedSequence = [[1, 2].async, [3, 4].async].async
let joinedSequence = nestedSequence.joined(separator: 0)
for await value in joinedSequence {
    print(value) // Output: 1, 2, 0, 3, 4
}

// MARK: - Creating Asynchronous Sequences

// async: Create an asynchronous sequence composed from a synchronous sequence.
let syncSequence = [1, 2, 3]
let asyncSequence = syncSequence.async
for await value in asyncSequence {
    print(value) // Output: 1, 2, 3
}

// AsyncChannel: An asynchronous sequence with back pressure sending semantics.
let channel = AsyncChannel<Int>()
Task {
    await channel.send(1)
    await channel.send(2)
    await channel.send(3)
    channel.finish()
}
for await value in channel {
    print(value) // Output: 1, 2, 3
}

// AsyncThrowingChannel: An asynchronous sequence with back pressure sending semantics that can emit failures.
let throwingChannel = AsyncThrowingChannel<Int, Error>()
Task {
    do {
        try await throwingChannel.send(1)
        try await throwingChannel.send(2)
        try await throwingChannel.send(3)
        throwingChannel.finish()
    } catch {
        throwingChannel.fail(error)
    }
}
do {
    for try await value in throwingChannel {
        print(value) // Output: 1, 2, 3
    }
} catch {
    print("Error: \(error)")
}

// MARK: - Performance Optimized Asynchronous Iterators

// AsyncBufferedByteIterator: A highly efficient iterator useful for iterating byte sequences 
// derived from asynchronous read functions.
let byteIterator = AsyncBufferedByteIterator(
    bufferingReads: { buffer in
        // Asynchronously fill the buffer with bytes from a data source
        // Return the number of bytes read
    }
)
for await byte in byteIterator {
    print(byte) // Output: individual bytes from the data source
}

// MARK: - Other Useful Asynchronous Sequences

// adjacentPairs: Collects tuples of adjacent elements.
let adjacentPairsSequence = [1, 2, 3, 4].async.adjacentPairs()
for await pair in adjacentPairsSequence {
    print(pair) // Output: (1, 2), (2, 3), (3, 4)
}

// chunks and chunked: Collect values into chunks.
let chunksSequence = [1, 2, 3, 4, 5].async.chunks(ofCount: 2)
for await chunk in chunksSequence {
    print(chunk) // Output: [1, 2], [3, 4], [5]
}

let chunkedSequence = [1, 2, 3, 4, 5].async.chunked(by: 2)
for await chunk in chunkedSequence {
    print(chunk) // Output: [1, 2], [3, 4], [5]
}

// compacted: Remove nil values from an asynchronous sequence.
let optionalSequence = [1, nil, 2, nil, 3].async
let compactedSequence = optionalSequence.compacted()
for await value in compactedSequence {
    print(value) // Output: 1, 2, 3
}

// removeDuplicates: Remove sequentially adjacent duplicate values.
let duplicateSequence = [1, 1, 2, 2, 3, 3].async
let uniqueSequence = duplicateSequence.removeDuplicates()
for await value in uniqueSequence {
    print(value) // Output: 1, 2, 3
}

// interspersed: Place a value between every two elements of an asynchronous sequence.
let interspersedSequence = [1, 2, 3].async.interspersed(with: 0)
for await value in interspersedSequence {
    print(value) // Output: 1, 0, 2, 0, 3
}

// MARK: - Asynchronous Sequences that Transact in Time

// debounce: Emit values after a quiescence period has been reached.
let debouncedSequence = [1, 2, 3, 4, 5].async.debounce(for: .seconds(1))
for await value in debouncedSequence {
    print(value) // Output: 5 (after a 1-second delay)
}

// throttle: Ensure a minimum interval has elapsed between events.
let throttledSequence = [1, 2, 3, 4, 5].async.throttle(for: .seconds(1))
for await value in throttledSequence {
    print(value) // Output: 1, 3, 5 (values emitted at 1-second intervals)
}

// AsyncTimerSequence: Emit the value of now at a given interval repeatedly.
let timerSequence = AsyncTimerSequence(interval: .seconds(1))
for await timestamp in timerSequence.prefix(3) {
    print(timestamp) // Output: current timestamps at 1-second intervals (3 times)
}

// MARK: - Obtaining All Values from an Asynchronous Sequence

// RangeReplaceableCollection.init: Creates a new instance of a collection containing the elements of an asynchronous sequence.
let collectedArray = try await Array(asyncSequence)
print(collectedArray) // Output: [1, 2, 3]

// Dictionary.init(uniqueKeysWithValues:): Creates a new dictionary from the key-value pairs in the given asynchronous sequence.
let keyValuePairs = [(1, "A"), (2, "B"), (3, "C")].async
let dictionary = try await Dictionary(uniqueKeysWithValues: keyValuePairs)
print(dictionary) // Output: [1: "A", 2: "B", 3: "C"]

// SetAlgebra.init: Creates a new set from an asynchronous sequence of items.
let set = try await Set(asyncSequence)
print(set) // Output: [1, 2, 3]
