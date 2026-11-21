pushd $(dirname $0)

# Clean up old image
podman stop -i wordle_tracker
podman rm -i wordle_tracker

# Build latest image and run container
podman build . -t wordle_tracker:latest
podman image prune -f

podman run \
    --name wordle_tracker \
    -i \
    -t \
    -m 2500m \
    --memory-reservation 2g \
    -v ./log:/wordle_tracker/log \
    -v ./resources/database:/wordle_tracker/resources/database \
    wordle_tracker:latest

popd