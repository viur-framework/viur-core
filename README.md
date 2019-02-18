# ViUR server

This is the main component of **ViUR**, a free software development framework for the [Google App Engine](https://appengine.google.com).

## About

ViUR provides a clear concept for implementing agile data management software that runs on top of the [Google App Engine](https://appengine.google.com) platform. It is written in the [Python programming language](https://python.org) for a maximum flexibility and easy-to-manage code. Its underlying database is Googles Cloud Datastore, which is a scalable document database.

The ViUR framework targets to the implementation of information systems, which are integrated, web-based applications or services performing data management and deployment operations of any kind. Therefore, ViUR is explicitly not claimed to be a content management system, although content management can be a part of a ViUR information system.

## Getting started

Visit [viur.is](https://www.viur.is/) to get latest news and documentation on ViUR and how it is used.

To quickly setup a running ViUR web-application from scratch, follow these simple steps:

1. Install the prerequisites [Python 2.7](https://www.python.org/downloads/) and [Google Cloud SDK for Python](https://cloud.google.com/sdk) for your operating system.
2. Create an empty folder for your project.
3. [Download setup.py](https://www.viur.is/package/download/setup/latest) and save it into the newly created folder.
4. Run ``python2 setup.py`` from that folder - it will do the rest for you!
5. Locally start the development server with ``dev_appserver.py -A <your-project-key> <project-dir>``
   or deploy it to the world with ``gcloud app deploy --project <your-project-key> <your-project-dir>``.

All quick start steps on a bash:

```bash
$ mkdir hello-viur                                                      # Setup project folder
$ cd hello-viur                                                         # Change into this folder
$ wget -qO setup.py https://www.viur.is/package/download/setup/latest   # Download latest setup
$ python setup.py                                                       # Run ViUR setup tool
$ dev_appserver.py -A hello-viur .                                      # Start Google App Engine
```

Visit the official [ViUR online documentation](https://docs.viur.is/latest) for more information.

## Contributing

We take a great interest in your opinion about ViUR. We appreciate your feedback and are looking forward to hear about your ideas. Share your visions or questions with us and participate in ongoing discussions.

- [ViUR website](https://www.viur.is)
- [#ViUR on freenode IRC](https://webchat.freenode.net/?channels=viur)
- [ViUR on GitHub](https://github.com/viur-framework)
- [ViUR on Twitter](https://twitter.com/weloveViUR)

## Credits

ViUR is developed and maintained by [Mausbrand Informationssysteme GmbH](https://www.mausbrand.de/en), from Dortmund in Germany. We are a software company consisting of young, enthusiastic software developers, designers and social media experts, working on exciting projects for different kinds of customers. All of our newer projects are implemented with ViUR, from tiny web-pages to huge company intranets with hundreds of users.

Help of any kind to extend and improve or enhance this project in any kind or way is always appreciated.

## License

Copyright (C) 2012-2019 by Mausbrand Informationssysteme GmbH.

Mausbrand and ViUR are registered trademarks of Mausbrand Informationssysteme GmbH.

You may use, modify and distribute this software under the terms and conditions of the GNU Lesser General Public License (LGPL). See the file LICENSE provided within this package for more information.
