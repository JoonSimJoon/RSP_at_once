#!/bin/bash
# Compile both agents
g++ -std=c++17 -O2 -o random_agent random_agent.cpp
g++ -std=c++17 -O2 -o greedy_agent greedy_agent.cpp
echo "Compiled: random_agent, greedy_agent"
