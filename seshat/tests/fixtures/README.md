# Offline face fixture

`astronaut.png` is scikit-image's sample NASA photograph of astronaut Eileen Collins.

- Source: https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png
- SHA-256: `88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`
- Attribution: NASA, via scikit-image. The [scikit-image documentation](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) states that the image was released into the public domain with no known copyright restrictions.

This fixture is only for offline model/API integration tests. It is not part of the runtime container, and it is never automatically enrolled in a user's database. Tests use a synthetic enrollment label and temporary storage.
