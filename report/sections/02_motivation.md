# 2. Motivation and purpose of the course project

Airlines and airports need to answer questions that no single flight record can answer: which routes carry the most passengers in a holiday week, which airports act as transit hubs, how fares move with distance and cabin class, and how stopover flights compare with direct ones. A data warehouse organises flight-segment records into subject-oriented dimensions (time, passenger, airport, flight, aircraft, cabin, price band) so that these questions can be asked quickly and repeatedly with OLAP operations such as drill down, roll up, slice, dice, ranking, top-N and moving averages [1].

The purpose of this project is to design and build such a warehouse for a flight journey management scenario, to prepare the supplied data so that it satisfies the course's data requirements (including stopover information), and to demonstrate the warehouse with a set of meaningful MDX analyses, with special attention to stopover flights.
