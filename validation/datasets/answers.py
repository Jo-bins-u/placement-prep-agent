"""Hand-written, realistic candidate answers with the band a fair interviewer would give.

Unlike the synthetic evaluator suite (which builds answers out of the rubric's own words),
these are phrased the way students actually answer: synonyms, informal wording, small typos,
partial knowledge, confident-but-wrong answers and off-topic ones. Used to measure how well
the rubric scorer tolerates different wording (the "paraphrase robustness" numbers).

band: "high" (>= 75), "mid" (40-74), "low" (< 40)
"""

ANSWERS = [
    # q001 array vs linked list
    ("q001", "high", "Arrays keep all elements next to each other in memory so you can jump straight to any index in "
                     "constant time, but growing them means copying. A linked list has nodes scattered around, each "
                     "with a reference to the next one, so adding or removing a node is cheap but reaching the k-th "
                     "item means walking the list."),
    ("q001", "mid", "An array is stored in one block of memory and you access by index. Linked list uses nodes."),
    ("q001", "low", "Both are the same thing, a linked list is just an array written in Java."),
    # q002 hash collisions
    ("q002", "high", "When two keys land in the same slot you either keep a small list per bucket and append to it "
                     "(separate chaining), or you look for the next free slot using linear or quadratic probing. When "
                     "the table gets too full you resize and rehash everything to keep lookups near O(1)."),
    ("q002", "mid", "If two keys hash to the same index, we store both in a linked list at that bucket."),
    ("q002", "low", "Hash tables never have collisions because every key is unique."),
    # q003 memoization vs tabulation
    ("q003", "high", "Memoization is the top down approach - you write the recursion and save each answer in a "
                     "dictionary so repeated subproblems are looked up instead of recomputed. Tabulation goes bottom up, "
                     "filling an array iteratively from the base cases, so there's no recursion depth problem."),
    ("q003", "mid", "Memoization uses recursion with a cache, tabulation uses loops."),
    ("q003", "low", "Memoization means memorising the answers before the exam."),
    # q009 deadlock
    ("q009", "high", "Deadlock is when processes wait on each other forever, each holding something the other needs. "
                     "It needs mutual exclusion, hold and wait, no pre-emption and a circular chain of waiting. If you "
                     "break any one, like always acquiring locks in a fixed order, it can't happen."),
    ("q009", "mid", "A deadlock is when two processes are stuck waiting for each other's resources forever."),
    ("q009", "low", "Deadlock is when the CPU is too slow and the program hangs for a while."),
    # q010 process vs thread
    ("q010", "high", "A process has its own separate memory space, while threads inside a process share the same memory. "
                     "Threads are lighter weight, so creating them and switching between them is cheaper, but a bug in "
                     "one thread can bring down the whole process."),
    ("q010", "mid", "Threads are smaller than processes and run inside a process."),
    ("q010", "low", "A thread is a process that runs on the GPU."),
    # q012 horizontal vs vertical scaling
    ("q012", "high", "Vertical scaling means upgrading one server with more CPU and RAM, which is easy but you hit a "
                     "limit and it's still one point of failure. Horizontal scaling means adding more servers and "
                     "putting a load balancer in front so traffic is spread out, which scales further."),
    ("q012", "mid", "Horizontal means adding more servers, vertical means making the server bigger."),
    ("q012", "low", "Horizontal scaling is scaling the width of the website layout and vertical is the height."),
    # q013 TCP vs UDP
    ("q013", "high", "TCP sets up a connection with a handshake and guarantees delivery by acknowledging and resending "
                     "lost packets in order. UDP just fires datagrams with no connection or guarantees, which makes it "
                     "quicker - good for video calls, games and DNS lookups."),
    ("q013", "mid", "TCP is reliable and UDP is not reliable but faster."),
    ("q013", "low", "TCP is for sending text and UDP is for sending pictures."),
    # q015 list vs tuple
    ("q015", "high", "Lists can be modified after creation, tuples can't - they are immutable. Because of that a tuple "
                     "can be used as a dict key and is a bit faster and lighter. Lists use [ ] and tuples use ( )."),
    ("q015", "mid", "List is mutable and tuple is not."),
    ("q015", "low", "A tuple is a list with only two elements."),
    # q017 overfitting
    ("q017", "high", "Overfitting is when the model memorises the training set including its noise, so it does great "
                     "in training but badly on new data. You can fight it with regularisation like L2, getting more "
                     "data, early stopping or dropout, and check it with a validation set."),
    ("q017", "mid", "When the model is too complex and does well only on training data. Use more data."),
    ("q017", "low", "Overfitting is when the dataset is too big to fit in memory."),
    # q019 ACID
    ("q019", "high", "A transaction is a set of operations that should act as one unit. Atomicity means all or nothing, "
                     "consistency keeps the data valid, isolation stops concurrent transactions from seeing half-done "
                     "work, and durability means once committed it survives a crash."),
    ("q019", "mid", "A transaction is a group of queries; ACID means atomic, consistent, isolated and durable."),
    ("q019", "low", "A transaction is when you pay money through the database."),
    # q007 polymorphism
    ("q007", "high", "Polymorphism lets you call the same method on different objects and each responds in its own "
                     "way. For instance a Shape class with area(), and Circle and Rectangle override it - at runtime the "
                     "right version runs. Method overloading is the compile time kind."),
    ("q007", "mid", "Polymorphism means many forms, like a function that behaves differently for different classes."),
    ("q007", "low", "Polymorphism is when a class has many variables."),
    # q020 load balancer
    ("q020", "high", "It spreads incoming requests over several servers so none gets overloaded, and if one dies the "
                     "health checks stop sending traffic to it, so the site stays up. A simple algorithm is round "
                     "robin; least connections is another."),
    ("q020", "mid", "A load balancer divides the traffic between servers."),
    ("q020", "low", "A load balancer balances the weight of the server rack."),
    # typos
    ("q013", "high", "TCP is conection oriented and relaible, it does a handshake and resends lost packets in order; "
                     "UDP is conectionless, no garantees, but faster so its used for streaming and games."),
    ("q010", "high", "Proceses have seperate memory, threads share the memory of their proces, threads are lighter and "
                     "context switching is cheaper, but one thread crashing can kill the proces."),
]
