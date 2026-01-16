#!/bin/bash

# Initialize and update git submodules
echo "Initializing git submodules..."
git submodule init
git submodule update --recursive

echo "Done! All submodules are ready."

