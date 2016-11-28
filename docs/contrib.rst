============
Contributing
============

This project is still young, so there is still plenty to be done. Contributions are more than welcome!

Please file tickets for discussion before submitting patches. Pull requests should target `master` and should leave Zappa in a "shippable" state if merged.

If you are adding a non-trivial amount of new code, please include a functioning test in your PR. For AWS calls, we use the placebo library, which you can learn to use [in the test writing guide](tests/README.md). The test suite will be run by [Travis CI](https://travis-ci.org/Miserlou/Zappa) once you open a pull request.

Please include the GitHub issue or pull request URL that has discussion related to your changes as a comment in the code ([example](https://github.com/Miserlou/Zappa/blob/fae2925431b820eaedf088a632022e4120a29f89/zappa/zappa.py#L241-L243)). This greatly helps for project maintainability, as it allows us to trace back use cases and explain decision making.

#### Using a Local Repo

To use the git HEAD, you *can't* use `pip install -e `. Instead, you should clone the repo to your machine and then `pip install /path/to/zappa/repo` or `ln -s /path/to/zappa/repo/zappa zappa` in your local project.
